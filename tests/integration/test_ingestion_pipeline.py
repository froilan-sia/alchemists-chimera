"""Integration tests for the complete PDF ingestion pipeline."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("pydantic")
pytest.importorskip("rdflib")

from src.ingestor.pdf_parser import PDFParser, PDFParserConfig
from src.ingestor.pipeline import IngestionPipeline, PipelineStatus
from src.ingestor.triple_extractor import ExtractedTriple, ExtractionStatus

SAMPLE_PDF = Path(__file__).parents[2] / "data" / "input" / "sample.pdf"


class RecordingVectorStore:
    """Small in-memory vector-store contract for pipeline integration tests."""

    def __init__(self):
        self.documents = []

    def add_documents(self, documents, metadata=None):
        self.documents.extend(zip(documents, metadata or [{} for _ in documents]))
        return [f"vector-{len(self.documents)}"]

    def health_check(self):
        return {"status": "healthy", "document_count": str(len(self.documents))}


class RecordingStagingManager:
    """Capture staged records without touching the repository's persistent data."""

    def __init__(self):
        self.records = []

    def add_record(self, record):
        self.records.append(record)
        return f"record-{len(self.records)}"

    def get_stats(self):
        return {
            "total_records": len(self.records),
            "pending_review": len(self.records),
            "status_counts": {},
        }


class StaticEntityExtractor:
    """Return deterministic anchors while exercising pipeline sequencing."""

    def extract_entities(self, text, chunk_id):
        return []


class GroundedAndUngroundedTripleExtractor:
    """Produce one valid source quote and one hallucinated quote per chunk."""

    def extract_triples_from_chunk(self, chunk, entities):
        grounded_quote = chunk.text[: min(len(chunk.text), 80)]
        if len(grounded_quote) < 10:
            grounded_quote = "The source contains capital."
        triples = [
            ExtractedTriple(
                subject="chimera:Source",
                predicate="chimera:mentions",
                object="chimera:Capital",
                evidence=grounded_quote,
                confidence=0.95,
                chunk_id=chunk.id,
                entity_anchors=["Source"],
                metadata={},
                extraction_timestamp=datetime.now(),
            ),
            ExtractedTriple(
                subject="chimera:Hallucinated",
                predicate="chimera:mentions",
                object="chimera:Claim",
                evidence="This fabricated evidence is absent.",
                confidence=0.95,
                chunk_id=chunk.id,
                entity_anchors=["Hallucinated"],
                metadata={},
                extraction_timestamp=datetime.now(),
            ),
        ]
        return triples, ExtractionStatus.SUCCESS


class AlwaysValidValidator:
    """Make SHACL classification observable without external ontology state."""

    def validate_and_classify(self, triple):
        return "valid", ["validation passed"]


class RecordingProvenanceManager:
    """Record every provenance call made by the orchestrator."""

    def __init__(self):
        self.records = []

    def create_provenance_record(self, triple, chunk, entities):
        record = SimpleNamespace(
            triple_id=triple.chunk_id,
            source_document=chunk.document_name,
            page_number=chunk.page_number,
            extraction_timestamp=datetime.now(),
        )
        self.records.append(record)
        return record


def build_pipeline(monkeypatch):
    """Build an injected pipeline around the real PDF parser."""
    pipeline = object.__new__(IngestionPipeline)
    pipeline.config = {"chunk_size": 1000, "chunk_overlap": 200}
    pipeline.pdf_parser = PDFParser(PDFParserConfig(chunk_size=1000, chunk_overlap=200))
    pipeline.entity_extractor = StaticEntityExtractor()
    pipeline.triple_extractor = GroundedAndUngroundedTripleExtractor()
    pipeline.provenance_manager = RecordingProvenanceManager()
    pipeline.shacl_validator = AlwaysValidValidator()
    pipeline.vector_store = RecordingVectorStore()
    pipeline.staging_manager = RecordingStagingManager()
    pipeline.metrics = __import__(
        "src.ingestor.pipeline", fromlist=["PipelineMetrics"]
    ).PipelineMetrics()
    pipeline.status = PipelineStatus.PENDING
    monkeypatch.setattr("src.ingestor.pipeline.time.sleep", lambda _: None)
    return pipeline


def test_complete_pipeline_filters_ungrounded_triples_and_stages_grounded_data(
    monkeypatch,
):
    """PDF text reaches vector storage and only grounded triples reach staging."""
    if not SAMPLE_PDF.exists():
        pytest.fail(f"repository sample PDF is missing: {SAMPLE_PDF}")

    pipeline = build_pipeline(monkeypatch)
    metrics = pipeline.process_pdf(SAMPLE_PDF)

    assert pipeline.status == PipelineStatus.COMPLETED
    assert metrics.total_chunks > 0
    assert metrics.processed_chunks == metrics.total_chunks
    assert metrics.failed_chunks == 0
    assert metrics.total_triples == metrics.total_chunks
    assert metrics.valid_triples == metrics.total_chunks
    assert metrics.quarantined_triples == 0
    assert metrics.vector_insertions == metrics.total_chunks
    assert len(pipeline.vector_store.documents) == metrics.total_chunks
    assert len(pipeline.staging_manager.records) == metrics.total_chunks
    assert all(
        record.triple.subject == "chimera:Source"
        for record in pipeline.staging_manager.records
    )
    assert len(pipeline.provenance_manager.records) == metrics.total_chunks


def test_pipeline_status_reports_metrics_and_store_health(monkeypatch):
    """Status output includes pipeline, staging, and vector-store health."""
    pipeline = build_pipeline(monkeypatch)
    pipeline.process_pdf(SAMPLE_PDF)

    status = pipeline.get_status()

    assert status["pipeline_status"] == "completed"
    assert status["metrics"]["total_chunks"] > 0
    assert status["metrics"]["vector_insertions"] == status["metrics"]["total_chunks"]
    assert status["staging"]["total_records"] == status["metrics"]["total_triples"]
    assert status["vector_store"]["status"] == "healthy"


def test_pipeline_reset_clears_processing_state(monkeypatch):
    """A pipeline can be reused after its metrics and status are reset."""
    pipeline = build_pipeline(monkeypatch)
    pipeline.process_pdf(SAMPLE_PDF)
    pipeline.reset()

    assert pipeline.status == PipelineStatus.PENDING
    assert pipeline.metrics.total_chunks == 0
    assert pipeline.metrics.total_triples == 0
    assert pipeline.metrics.start_time is None


def test_pipeline_rejects_missing_pdf(monkeypatch, tmp_path):
    """Missing input documents fail before component processing begins."""
    pipeline = build_pipeline(monkeypatch)

    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        pipeline.process_pdf(tmp_path / "missing.pdf")
