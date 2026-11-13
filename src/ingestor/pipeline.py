"""
Ingestion Pipeline Orchestrator for Alchemist's Chimera.

Orchestrates the complete document ingestion workflow with sequential processing
to maintain stable memory and CPU usage on Hugging Face Spaces.

Responsibilities:
1. Sequential chunk processing (no parallelization)
2. Complete workflow coordination of 5 ingestor components
3. Evidence grounding verification
4. Vector store integration for immediate hybrid retrieval
5. Comprehensive error handling and recovery
6. HITL workflow with staging manager
"""

import logging
import time
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..config import settings
from ..performance import (
    PerformanceConfig,
    PerformanceMonitor,
    ResourceLimiter,
    ResourceLimitError,
)
from ..vector_store import VectorStore
from .entity_extractor import EntityExtractor, EntityExtractorConfig, ExtractedEntity

# Local imports
from .pdf_parser import PDFChunk, PDFParser, PDFParserConfig
from .provenance_manager import ProvenanceManager, ProvenanceRecord, ProvenanceStatus
from .shacl_validator import SHACLValidator, ValidationResult
from .triple_extractor import (
    ExtractedTriple,
    ExtractionStatus,
    TripleExtractor,
    TripleExtractorConfig,
)

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    """Status of pipeline processing."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ValidationStatus(str, Enum):
    """Status of triple validation."""

    VALID = "valid"
    INVALID = "invalid"
    QUARANTINED = "quarantined"
    PENDING_REVIEW = "pending_review"


@dataclass
class StagingRecord:
    """Record for HITL (Human-In-The-Loop) staging."""

    triple: ExtractedTriple
    validation_status: ValidationStatus
    validation_messages: List[str]
    provenance_record: Optional[ProvenanceRecord]
    quarantine_reason: Optional[str] = None
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    review_timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineMetrics:
    """Metrics for pipeline execution."""

    total_chunks: int = 0
    processed_chunks: int = 0
    failed_chunks: int = 0
    total_triples: int = 0
    valid_triples: int = 0
    quarantined_triples: int = 0
    vector_insertions: int = 0
    parallel_batches: int = 0
    preprocessing_workers: int = 1
    peak_memory_mb: float = 0.0
    performance: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    processing_times: Dict[str, float] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate of chunk processing."""
        if self.total_chunks == 0:
            return 0.0
        return self.processed_chunks / self.total_chunks

    @property
    def validation_rate(self) -> float:
        """Calculate validation rate of triples."""
        if self.total_triples == 0:
            return 0.0
        return self.valid_triples / self.total_triples

    @property
    def duration_seconds(self) -> float:
        """Calculate total duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class IngestionPipeline:
    """Main ingestion pipeline orchestrator."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize ingestion pipeline with all components.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.checkpoint_path = Path(self.config.get("checkpoint_path", "./data/tmp/ingestion_checkpoint.json"))
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_checkpoint: Optional[Dict[str, Any]] = None
        self.performance_config = PerformanceConfig(
            batch_size=self.config.get(
                "batch_size", getattr(settings, "ingestion_batch_size", 8)
            ),
            max_workers=self.config.get(
                "max_workers", getattr(settings, "ingestion_max_workers", 2)
            ),
            chunk_timeout_seconds=self.config.get(
                "chunk_timeout_seconds",
                getattr(settings, "ingestion_chunk_timeout_seconds", 120.0),
            ),
            pdf_timeout_seconds=self.config.get(
                "pdf_timeout_seconds",
                getattr(settings, "ingestion_pdf_timeout_seconds", 300.0),
            ),
            memory_limit_mb=self.config.get(
                "memory_limit_mb", getattr(settings, "ingestion_memory_limit_mb", 2048)
            ),
            max_chunks=self.config.get(
                "max_chunks", getattr(settings, "ingestion_max_chunks", 10000)
            ),
            database_pool_size=self.config.get(
                "database_pool_size", getattr(settings, "database_pool_size", 4)
            ),
            enable_parallel_preprocessing=self.config.get(
                "enable_parallel_preprocessing", True
            ),
        )
        self.performance_monitor = PerformanceMonitor()

        # Initialize components
        logger.info("Initializing ingestion pipeline components...")

        # 1. PDF Parser
        pdf_config = PDFParserConfig(
            chunk_size=self.config.get("chunk_size", 1000),
            chunk_overlap=self.config.get("chunk_overlap", 200),
        )
        self.pdf_parser = PDFParser(pdf_config)

        # 2. Entity Extractor
        entity_config = EntityExtractorConfig(
            entity_types=self.config.get(
                "entity_types", ["ORG", "PERSON", "LAW", "MONEY", "GPE"]
            ),
            min_confidence=self.config.get("min_entity_confidence", 0.5),
        )
        self.entity_extractor = EntityExtractor(entity_config)

        # 3. Triple Extractor
        triple_config = TripleExtractorConfig(
            ollama_base_url=self.config.get(
                "ollama_base_url", "http://localhost:11434"
            ),
            model_name=self.config.get("model_name", "qwen2.5:3b"),
            confidence_threshold=self.config.get("confidence_threshold", 0.5),
            ontology_path=self.config.get(
                "ontology_path", "./ontology/finance-ontology.ttl"
            ),
            connection_pool_size=1,
        )
        self.triple_extractor = TripleExtractor(triple_config)

        # 4. Provenance Manager
        self.provenance_manager = ProvenanceManager(
            base_uri=self.config.get("base_uri", "http://alchemists-chimera.org/")
        )

        # 5. SHACL Validator
        shapes_file = self.config.get("shapes_file")
        if shapes_file:
            shapes_file = Path(shapes_file)
        self.shacl_validator = SHACLValidator(
            shapes_file, self.config.get("base_uri", "http://alchemists-chimera.org/")
        )

        # 6. Vector Store
        self.vector_store = VectorStore(
            persist_directory=self.config.get(
                "vector_store_path", "./data/vector_store"
            )
        )
        self.vector_store.initialize()

        # 7. Comprehensive Staging Manager with backward compatibility
        from .staging_adapter import get_staging_manager

        staging_path = self.config.get("staging_path", "./data/staging")
        self.staging_manager = get_staging_manager(
            Path(staging_path), use_comprehensive=True
        )

        # Pipeline state
        self.metrics = PipelineMetrics()
        self.status = PipelineStatus.PENDING

        logger.info("Ingestion pipeline initialized successfully")
        logger.info(
            f"Using components: PDF Parser, Entity Extractor, Triple Extractor, "
            f"Provenance Manager, SHACL Validator, Vector Store, Comprehensive Staging Manager"
        )

    def _document_key(self, pdf_path: Path) -> str:
        """Create a stable checkpoint key for a source file."""
        stat = pdf_path.stat()
        return hashlib.sha256(f"{pdf_path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()

    def _load_checkpoint(self, pdf_path: Path) -> Dict[str, Any]:
        """Load a matching checkpoint, treating malformed state as recoverable."""
        checkpoint_path = getattr(self, "checkpoint_path", Path("./data/tmp/ingestion_checkpoint.json"))
        self.checkpoint_path = checkpoint_path
        if not checkpoint_path.exists():
            return {"document_key": self._document_key(pdf_path), "processed_chunks": []}
        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if data.get("document_key") != self._document_key(pdf_path):
                return {"document_key": self._document_key(pdf_path), "processed_chunks": []}
            return data
        except (OSError, ValueError, TypeError) as error:
            backup = checkpoint_path.with_suffix(
                f".corrupt.{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            )
            try:
                checkpoint_path.replace(backup)
            except OSError:
                logger.error("Unable to back up corrupt checkpoint: %s", error)
            logger.error("Ignoring corrupt ingestion checkpoint: %s", error)
            return {"document_key": self._document_key(pdf_path), "processed_chunks": []}

    def _save_checkpoint(self, state: Dict[str, Any]) -> None:
        """Persist checkpoint state atomically after each completed batch."""
        checkpoint_path = getattr(self, "checkpoint_path", Path("./data/tmp/ingestion_checkpoint.json"))
        self.checkpoint_path = checkpoint_path
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = checkpoint_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        temporary_path.replace(checkpoint_path)
        self._active_checkpoint = state

    def clear_checkpoint(self) -> None:
        """Remove the completed or abandoned ingestion checkpoint."""
        try:
            self.checkpoint_path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("Unable to clear ingestion checkpoint: %s", error)
        self._active_checkpoint = None

    def recover_interrupted_process(self) -> Optional[Dict[str, Any]]:
        """Return recoverable checkpoint data without starting ingestion."""
        if not self.checkpoint_path.exists():
            return None
        try:
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            logger.error("Unable to read interrupted-ingestion checkpoint: %s", error)
            return None

    def health_check(self) -> Dict[str, Any]:
        """Return health for every pipeline component and recovery state."""
        components = {}
        for name, component in {
            "pdf_parser": getattr(self, "pdf_parser", None),
            "entity_extractor": getattr(self, "entity_extractor", None),
            "triple_extractor": getattr(self, "triple_extractor", None),
            "shacl_validator": getattr(self, "shacl_validator", None),
            "staging_manager": getattr(self, "staging_manager", None),
            "vector_store": getattr(self, "vector_store", None),
        }.items():
            try:
                if component is None:
                    components[name] = {"status": "uninitialized"}
                elif hasattr(component, "health_check"):
                    components[name] = component.health_check()
                else:
                    components[name] = {"status": "initialized"}
            except Exception as error:
                logger.error("Health check failed for %s: %s", name, error, exc_info=True)
                components[name] = {"status": "unhealthy", "error": str(error)}
        statuses = [value.get("status", "unhealthy") for value in components.values()]
        status = "healthy" if statuses and all(value == "healthy" for value in statuses) else "degraded"
        return {
            "status": status,
            "component": "ingestion_pipeline",
            "pipeline_status": getattr(self, "status", PipelineStatus.PENDING).value,
            "checkpoint": str(getattr(self, "checkpoint_path", "")),
            "checkpoint_present": bool(getattr(self, "checkpoint_path", None) and self.checkpoint_path.exists()),
            "components": components,
        }

    def process_documents(self, pdf_paths: List[Union[str, Path]]) -> Dict[str, PipelineMetrics]:
        """Process documents independently so one corrupt PDF cannot stop the batch."""
        results: Dict[str, PipelineMetrics] = {}
        for pdf_path in pdf_paths:
            try:
                results[str(pdf_path)] = self.process_pdf(pdf_path)
            except (FileNotFoundError, PipelineError) as error:
                logger.error("Skipping failed document %s: %s", pdf_path, error)
        return results

    def process_pdf(self, pdf_path: Union[str, Path]) -> PipelineMetrics:
        """Process a PDF file through the complete ingestion pipeline.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Pipeline metrics

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            PipelineError: If pipeline processing fails
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info("Starting ingestion pipeline for: %s", pdf_path)
        checkpoint = self._load_checkpoint(pdf_path)
        processed_chunk_ids = set(checkpoint.get("processed_chunks", []))
        self._active_checkpoint = checkpoint
        self.status = PipelineStatus.IN_PROGRESS
        self.metrics.start_time = datetime.now()

        limiter = ResourceLimiter(getattr(self, "performance_config", PerformanceConfig()))
        monitor = getattr(self, "performance_monitor", PerformanceMonitor())
        self.performance_monitor = monitor
        self.metrics.preprocessing_workers = (
            self.performance_config.max_workers
            if getattr(self, "performance_config", None)
            else 1
        )

        try:
            # Consume the parser's generator in bounded batches. This keeps page
            # extraction streaming while allowing CPU-bound preprocessing to run
            # concurrently without retaining a whole large PDF unnecessarily.
            logger.info("Step 1: Streaming PDF parsing and bounded preprocessing...")
            parse_start = time.perf_counter()
            batch: List[PDFChunk] = []
            batch_size = getattr(
                getattr(self, "performance_config", None), "batch_size", 8
            )
            with monitor.measure("pdf_parsing"):
                for chunk in self.pdf_parser.parse_pdf_streaming(pdf_path):
                    if chunk.id in processed_chunk_ids:
                        logger.info("Skipping checkpointed chunk %s", chunk.id)
                        continue
                    self.metrics.total_chunks += 1
                    limiter.check(self.metrics.total_chunks)
                    batch.append(chunk)
                    if len(batch) >= batch_size:
                        self._process_chunk_batch(batch, limiter, monitor)
                        checkpoint.setdefault("processed_chunks", []).extend(item.id for item in batch)
                        self._save_checkpoint(checkpoint)
                        batch = []
                if batch:
                    self._process_chunk_batch(batch, limiter, monitor)
                    checkpoint.setdefault("processed_chunks", []).extend(item.id for item in batch)
                    self._save_checkpoint(checkpoint)
            self.metrics.processing_times["pdf_parsing"] = time.perf_counter() - parse_start

            if not self.metrics.total_chunks:
                logger.warning("No chunks extracted from PDF")
                self.status = PipelineStatus.FAILED
                self.metrics.end_time = datetime.now()
                return self.metrics

            self.status = (
                PipelineStatus.COMPLETED
                if self.metrics.failed_chunks == 0
                else PipelineStatus.PARTIAL
            )
            self.metrics.end_time = datetime.now()
            self.metrics.peak_memory_mb = limiter.memory_usage_mb
            self.metrics.performance = monitor.snapshot()
            self._log_pipeline_summary()
            if self.status == PipelineStatus.COMPLETED:
                self.clear_checkpoint()
            return self.metrics

        except ResourceLimitError as error:
            logger.error("Pipeline resource limit reached: %s", error)
            self.status = PipelineStatus.PARTIAL
            self.metrics.end_time = datetime.now()
            self.metrics.peak_memory_mb = limiter.memory_usage_mb
            self.metrics.performance = monitor.snapshot()
            raise PipelineError(str(error)) from error
        except Exception as e:
            logger.error("Pipeline processing failed: %s", e, exc_info=True)
            self.status = PipelineStatus.FAILED
            self.metrics.end_time = datetime.now()
            if self._active_checkpoint is not None:
                self._active_checkpoint["status"] = self.status.value
                try:
                    self._save_checkpoint(self._active_checkpoint)
                except OSError as checkpoint_error:
                    logger.error("Unable to save recovery checkpoint: %s", checkpoint_error)
            raise PipelineError(f"Pipeline processing failed: {e}") from e

    def _process_chunk_batch(
        self,
        chunks: List[PDFChunk],
        limiter: ResourceLimiter,
        monitor: PerformanceMonitor,
    ) -> None:
        """Preprocess chunks in parallel, then extract with Ollama sequentially.

        Entity extraction is CPU-bound and safe to parallelize. The LLM call is
        deliberately kept in input order and runs one chunk at a time. Vector
        writes happen once per batch to reduce persistent-store overhead.
        """
        if not chunks:
            return
        self.metrics.parallel_batches += 1
        entity_map: Dict[str, List[ExtractedEntity]] = {}
        workers = getattr(
            getattr(self, "performance_config", None), "max_workers", 1
        )
        parallel = getattr(
            getattr(self, "performance_config", None),
            "enable_parallel_preprocessing",
            False,
        ) and workers > 1 and len(chunks) > 1

        def extract_entities(chunk: PDFChunk):
            return chunk.id, self.entity_extractor.extract_entities(chunk.text, chunk.id)

        with monitor.measure("entity_preprocessing"):
            if parallel:
                with ThreadPoolExecutor(max_workers=min(workers, len(chunks))) as pool:
                    futures = [pool.submit(extract_entities, chunk) for chunk in chunks]
                    for future in futures:
                        try:
                            chunk_id, entities = future.result(
                                timeout=getattr(
                                    self.performance_config,
                                    "chunk_timeout_seconds",
                                    120.0,
                                )
                            )
                            entity_map[chunk_id] = entities
                        except FutureTimeoutError as error:
                            logger.error("Entity preprocessing timed out for batch chunk: %s", error)
                            entity_map[chunk.id] = []
                        except Exception as error:
                            logger.error("Entity extraction failed for chunk %s: %s", chunks[len(entity_map)].id if len(entity_map) < len(chunks) else "unknown", error, exc_info=True)
                            if len(entity_map) < len(chunks):
                                entity_map[chunks[len(entity_map)].id] = []
            else:
                for chunk in chunks:
                    try:
                        chunk_id, entities = extract_entities(chunk)
                    except Exception as error:
                        logger.error("Entity extraction failed for chunk %s: %s", chunk.id, error, exc_info=True)
                        chunk_id, entities = chunk.id, []
                    entity_map[chunk_id] = entities

        # Never submit these calls to the executor. TripleExtractor owns the
        # sequential Ollama request path required by Hugging Face Spaces.
        for chunk in chunks:
            limiter.check()
            try:
                self._process_chunk(
                    chunk,
                    entities=entity_map.get(chunk.id, []),
                    insert_vector=False,
                )
                self.metrics.processed_chunks += 1
            except Exception as error:
                logger.error("Failed to process chunk %s: %s", chunk.id, error)
                self.metrics.failed_chunks += 1
            finally:
                monitor.increment("chunks_processed")

        self._insert_chunk_batch(chunks, monitor)
    def _insert_chunk_batch(
        self, chunks: List[PDFChunk], monitor: PerformanceMonitor
    ) -> None:
        """Persist one batch of chunks using one pooled vector-store operation."""
        documents = [chunk.text for chunk in chunks]
        metadata = [
            {
                "chunk_id": chunk.id,
                "page_number": chunk.page_number,
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "processed_time": datetime.now().isoformat(),
            }
            for chunk in chunks
        ]
        try:
            with monitor.measure("vector_store_batch_insert"):
                try:
                    ids = self.vector_store.add_documents(
                        documents=documents,
                        metadata=metadata,
                        ids=[chunk.id for chunk in chunks],
                    )
                except TypeError:
                    # Preserve compatibility with injected test stores and older
                    # VectorStore implementations that do not accept stable IDs.
                    ids = self.vector_store.add_documents(
                        documents=documents, metadata=metadata
                    )
            inserted = len(chunks) if ids else 0
            self.metrics.vector_insertions += inserted
            monitor.increment("vector_documents_inserted", inserted)
        except Exception as error:
            logger.error("Failed to insert chunk batch into vector store: %s", error)

    def _process_chunk(
        self,
        chunk: PDFChunk,
        entities: Optional[List[ExtractedEntity]] = None,
        insert_vector: bool = True,
    ) -> None:
        """Process one chunk while keeping Ollama extraction sequential."""
        chunk_start_time = time.time()

        # Step 2: Extract entities, or use the bounded parallel preprocessing result.
        logger.debug(f"Extracting entities from chunk {chunk.id}")
        entity_start = time.time()
        if entities is None:
            entities = self.entity_extractor.extract_entities(chunk.text, chunk.id)
        entity_time = time.time() - entity_start
        logger.debug(f"Extracted {len(entities)} entities in {entity_time:.2f}s")

        # Step 3: Extract triples
        logger.debug(f"Extracting triples from chunk {chunk.id}")
        triple_start = time.time()
        triples, extraction_status = self.triple_extractor.extract_triples_from_chunk(
            chunk, entities
        )
        triple_time = time.time() - triple_start
        logger.debug(f"Extracted {len(triples)} triples in {triple_time:.2f}s")

        if not triples:
            logger.warning(f"No triples extracted from chunk {chunk.id}")

        # Step 4: Verify evidence grounding (verbatim substring checks).
        # Ungrounded candidates must never reach validation or staging.
        logger.debug(f"Verifying evidence grounding for {len(triples)} triples")
        grounded_triples = [
            triple
            for triple in triples
            if self._verify_evidence_grounding(triple, chunk.text)
        ]
        if len(grounded_triples) != len(triples):
            logger.warning(
                "Filtered %d ungrounded triples from chunk %s",
                len(triples) - len(grounded_triples),
                chunk.id,
            )
        triples = grounded_triples

        # Step 5: Validate triples with SHACL and classify
        logger.debug(f"Validating {len(triples)} triples with SHACL")
        for triple in triples:
            # Use SHACL validator's classification method
            (
                classification,
                validation_messages,
            ) = self.shacl_validator.validate_and_classify(triple)

            # Map classification to ValidationStatus
            if classification == "valid":
                val_status = ValidationStatus.VALID
                self.metrics.valid_triples += 1
            elif classification == "quarantined":
                val_status = ValidationStatus.QUARANTINED
                self.metrics.quarantined_triples += 1
            else:  # "invalid"
                val_status = ValidationStatus.INVALID

            # Update metrics
            self.metrics.total_triples += 1

            # Create provenance record only for valid/quarantined triples
            provenance_record = None
            if val_status != ValidationStatus.INVALID:
                provenance_record = self.provenance_manager.create_provenance_record(
                    triple, chunk, entities
                )

            # Create staging record for backward compatibility
            staging_record = StagingRecord(
                triple=triple,
                validation_status=val_status,
                validation_messages=validation_messages,
                provenance_record=provenance_record,
                quarantine_reason=validation_messages[0]
                if val_status == ValidationStatus.QUARANTINED and validation_messages
                else None,
                metadata={
                    "chunk_id": chunk.id,
                    "extraction_status": extraction_status.value,
                    "entity_count": len(entities),
                    "classification": classification,
                },
            )

            # Send to the compliance staging manager (HITL workflow).
            # The default adapter keeps VALID candidates pending until a reviewer acts.
            self.staging_manager.add_record(staging_record)

        # Step 6: Batch vector insertion is handled by _process_chunk_batch.
        # Keep the direct method useful for callers that process one chunk.
        if insert_vector:
            self._insert_chunk_batch(
                [chunk], getattr(self, "performance_monitor", PerformanceMonitor())
            )

        chunk_total_time = time.time() - chunk_start_time
        logger.info(
            f"Processed chunk {chunk.id} in {chunk_total_time:.2f}s "
            f"(entities: {len(entities)}, triples: {len(triples)}, "
            f"valid: {self.metrics.valid_triples}, quarantined: {self.metrics.quarantined_triples})"
        )

    def _verify_evidence_grounding(
        self, triple: ExtractedTriple, original_text: str
    ) -> bool:
        """Verify evidence quote is a verbatim substring of original text.

        Args:
            triple: Extracted triple with evidence
            original_text: Original text from chunk

        Returns:
            True if evidence is grounded, False otherwise
        """
        evidence = triple.evidence.strip()

        if not evidence:
            logger.warning(
                f"Empty evidence for triple: {triple.subject} {triple.predicate} {triple.object}"
            )
            return False

        # Case-insensitive substring check
        evidence_lower = evidence.lower()
        original_lower = original_text.lower()

        if evidence_lower not in original_lower:
            logger.warning(f"Evidence not found in original text: '{evidence}'")
            return False

        # Additional check: evidence should be reasonably long
        if len(evidence) < 10:
            logger.warning(f"Evidence too short ({len(evidence)} chars): '{evidence}'")
            return False

        logger.debug(f"Evidence grounded successfully: '{evidence[:50]}...'")
        return True

    def _log_pipeline_summary(self) -> None:
        """Log pipeline execution summary."""
        logger.info("=" * 60)
        logger.info("INGESTION PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Status: {self.status.value}")
        logger.info(f"Duration: {self.metrics.duration_seconds:.2f}s")
        logger.info(f"Total chunks: {self.metrics.total_chunks}")
        logger.info(f"Processed chunks: {self.metrics.processed_chunks}")
        logger.info(f"Failed chunks: {self.metrics.failed_chunks}")
        logger.info(f"Success rate: {self.metrics.success_rate:.1%}")
        logger.info(f"Total triples: {self.metrics.total_triples}")
        logger.info(f"Valid triples: {self.metrics.valid_triples}")
        logger.info(f"Quarantined triples: {self.metrics.quarantined_triples}")
        logger.info(f"Validation rate: {self.metrics.validation_rate:.1%}")
        logger.info(f"Vector insertions: {self.metrics.vector_insertions}")

        # Log processing times
        logger.info("Processing times:")
        for stage, duration in self.metrics.processing_times.items():
            logger.info(f"  {stage}: {duration:.2f}s")

        # Log staging manager stats
        staging_stats = self.staging_manager.get_stats()
        logger.info("Staging manager:")
        logger.info(f"  Total records: {staging_stats['total_records']}")
        logger.info(f"  Pending review: {staging_stats['pending_review']}")
        logger.info(f"  Status counts: {staging_stats['status_counts']}")

        logger.info("=" * 60)

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status.

        Returns:
            Dictionary with pipeline status information
        """
        staging_stats = self.staging_manager.get_stats()

        return {
            "pipeline_status": self.status.value,
            "metrics": {
                "total_chunks": self.metrics.total_chunks,
                "processed_chunks": self.metrics.processed_chunks,
                "failed_chunks": self.metrics.failed_chunks,
                "success_rate": self.metrics.success_rate,
                "total_triples": self.metrics.total_triples,
                "valid_triples": self.metrics.valid_triples,
                "quarantined_triples": self.metrics.quarantined_triples,
                "validation_rate": self.metrics.validation_rate,
                "vector_insertions": self.metrics.vector_insertions,
                "duration_seconds": self.metrics.duration_seconds,
                "parallel_batches": self.metrics.parallel_batches,
                "preprocessing_workers": self.metrics.preprocessing_workers,
                "peak_memory_mb": self.metrics.peak_memory_mb,
            },
            "performance": getattr(
                self, "performance_monitor", PerformanceMonitor()
            ).snapshot(),
            "resource_limits": getattr(
                getattr(self, "performance_config", None), "model_dump", lambda: {}
            )(),
            "staging": staging_stats,
            "vector_store": self.vector_store.health_check(),
        }

    def reset(self) -> None:
        """Reset pipeline state for new processing."""
        self.metrics = PipelineMetrics()
        self.performance_monitor = PerformanceMonitor()
        self.status = PipelineStatus.PENDING
        logger.info("Pipeline reset for new processing")


class PipelineError(Exception):
    """Custom exception for pipeline errors."""

    pass


# Factory function for easy pipeline creation
def create_default_pipeline() -> IngestionPipeline:
    """Create an ingestion pipeline with default configuration.

    Returns:
        IngestionPipeline instance with default config
    """
    config = {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "entity_types": ["ORG", "PERSON", "LAW", "MONEY", "GPE"],
        "min_entity_confidence": 0.5,
        "ollama_base_url": "http://localhost:11434",
        "model_name": "qwen2.5:3b",
        "confidence_threshold": 0.5,
        "base_uri": "http://alchemists-chimera.org/",
        "vector_store_path": "./data/vector_store",
        "staging_path": "./data/staging",
    }

    return IngestionPipeline(config)


def main():
    """Example usage and testing of ingestion pipeline."""
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_file>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    try:
        print("Testing Ingestion Pipeline...")
        print("=" * 60)

        # Create pipeline
        pipeline = create_default_pipeline()

        # Process PDF
        print(f"Processing PDF: {pdf_path}")
        metrics = pipeline.process_pdf(pdf_path)

        # Display results
        print("\nPipeline execution complete!")
        print(f"Status: {pipeline.status.value}")
        print(f"Duration: {metrics.duration_seconds:.2f}s")
        print(f"Total chunks: {metrics.total_chunks}")
        print(f"Processed chunks: {metrics.processed_chunks}")
        print(f"Failed chunks: {metrics.failed_chunks}")
        print(f"Success rate: {metrics.success_rate:.1%}")
        print(f"Total triples: {metrics.total_triples}")
        print(f"Valid triples: {metrics.valid_triples}")
        print(f"Quarantined triples: {metrics.quarantined_triples}")
        print(f"Validation rate: {metrics.validation_rate:.1%}")
        print(f"Vector insertions: {metrics.vector_insertions}")

        # Get pipeline status
        status = pipeline.get_status()
        print(f"\nStaging records: {status['staging']['total_records']}")
        print(f"Pending review: {status['staging']['pending_review']}")
        print(f"Status counts: {status['staging']['status_counts']}")

        # Vector store health
        vector_health = status["vector_store"]
        print(f"\nVector store: {vector_health.get('status', 'unknown')}")
        print(f"Document count: {vector_health.get('document_count', '0')}")

        print("\n✅ Ingestion pipeline test completed successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
