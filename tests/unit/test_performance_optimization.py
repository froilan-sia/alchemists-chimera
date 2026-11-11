"""Unit coverage for bounded ingestion performance controls."""

import threading
import time
from datetime import datetime

from src.ingestor.pdf_parser import PDFChunk
from src.ingestor.pipeline import IngestionPipeline, PipelineMetrics, PipelineStatus
from src.performance import (
    DatabaseConnectionPool,
    FileContentCache,
    PerformanceConfig,
    PerformanceMonitor,
    ResourceLimiter,
)


def test_file_content_cache_reuses_and_invalidates_by_mtime(tmp_path):
    """Ontology/SHACL reads reuse content until the source file changes."""
    source = tmp_path / "shapes.ttl"
    source.write_text("initial", encoding="utf-8")

    FileContentCache.clear()
    assert FileContentCache.get_text(source) == "initial"
    source.write_text("updated", encoding="utf-8")
    assert FileContentCache.get_text(source) == "updated"


def test_connection_pool_bounds_active_operations():
    """The persistence pool never exceeds its configured capacity."""
    pool = DatabaseConnectionPool(max_connections=2)
    active = []
    lock = threading.Lock()

    def operation():
        with pool.connection():
            with lock:
                active.append(pool.status()["active_connections"])
            time.sleep(0.01)

    threads = [threading.Thread(target=operation) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max(active) <= 2
    assert pool.status()["active_connections"] == 0


def test_resource_limiter_exposes_configured_limits():
    """Resource controls are serializable for monitoring and deployment checks."""
    config = PerformanceConfig(batch_size=3, max_workers=2, max_chunks=12)
    limiter = ResourceLimiter(config)

    assert config.model_dump()["batch_size"] == 3
    assert limiter.memory_usage_mb >= 0
    limiter.check(chunks_seen=12)


class _ConcurrentEntityExtractor:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def extract_entities(self, text, chunk_id):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        with self.lock:
            self.active -= 1
        return []


class _SequentialTripleExtractor:
    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def extract_triples_from_chunk(self, chunk, entities):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.005)
        with self.lock:
            self.active -= 1
        return [], type("Status", (), {"value": "success"})()


class _VectorStore:
    def __init__(self):
        self.ids = []

    def add_documents(self, documents, metadata=None, ids=None):
        self.ids.extend(ids or [])
        return ids or []

    def health_check(self):
        return {"status": "healthy", "document_count": str(len(self.ids))}


class _StagingManager:
    def get_stats(self):
        return {"total_records": 0, "pending_review": 0, "status_counts": {}}


def test_pipeline_parallelizes_preprocessing_but_serializes_llm_calls():
    """CPU preprocessing may overlap while qwen2.5-style extraction never does."""
    pipeline = object.__new__(IngestionPipeline)
    pipeline.performance_config = PerformanceConfig(
        batch_size=4, max_workers=3, enable_parallel_preprocessing=True
    )
    pipeline.performance_monitor = PerformanceMonitor()
    pipeline.metrics = PipelineMetrics()
    pipeline.status = PipelineStatus.PENDING
    pipeline.entity_extractor = _ConcurrentEntityExtractor()
    pipeline.triple_extractor = _SequentialTripleExtractor()
    pipeline.shacl_validator = type(
        "Validator", (), {"validate_and_classify": lambda *_: ("valid", [])}
    )()
    pipeline.provenance_manager = type(
        "Provenance", (), {"create_provenance_record": lambda *_: None}
    )()
    pipeline.staging_manager = _StagingManager()
    pipeline.vector_store = _VectorStore()

    chunks = [
        PDFChunk(
            id=f"chunk-{index}",
            text="A sufficiently long source statement for processing.",
            page_number=1,
            chunk_index=index,
            total_chunks=4,
            metadata={},
            start_char=0,
            end_char=50,
            document_id="doc",
            document_name="source.pdf",
        )
        for index in range(4)
    ]
    pipeline._process_chunk_batch(
        chunks, ResourceLimiter(pipeline.performance_config), pipeline.performance_monitor
    )

    assert pipeline.entity_extractor.max_active > 1
    assert pipeline.triple_extractor.max_active == 1
    assert pipeline.metrics.vector_insertions == len(chunks)
