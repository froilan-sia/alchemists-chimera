"""Error-injection, recovery, and health checks for Task 18."""

from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from pydantic import ValidationError

from src.ingestor.pdf_parser import PDFChunk, PDFParser, PDFParserConfig
from src.ingestor.pipeline import IngestionPipeline, PipelineStatus
from src.ingestor.shacl_validator import SHACLValidator
from src.ingestor.triple_extractor import (
    ExtractedTriple,
    ExtractionStatus,
    TripleExtractor,
    TripleExtractorConfig,
    TripleExtractorError,
)
from src.staging_manager import StagingManager
from src.ingestor.pipeline import ValidationStatus


def _triple() -> ExtractedTriple:
    return ExtractedTriple(
        subject="chimera:Bank",
        predicate="chimera:requires",
        object="chimera:Capital",
        evidence="The bank must maintain capital requirements.",
        confidence=0.9,
        chunk_id="chunk-1",
        entity_anchors=["Bank"],
        metadata={},
        extraction_timestamp=datetime.now(),
    )


def test_pdf_batch_skips_corrupt_document_and_records_error(tmp_path: Path):
    """A corrupt upload is isolated from the rest of a document batch."""
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a pdf")
    parser = PDFParser(PDFParserConfig())

    assert parser.parse_documents([corrupt]) == {}
    assert parser.documents_failed >= 1
    assert parser.last_errors
    assert "Stream has ended" in parser.last_errors[-1]["error"]


def test_ollama_retry_uses_exponential_backoff(monkeypatch):
    """Transient Ollama errors retry with base, doubled, then successful delay."""
    extractor = TripleExtractor(
        TripleExtractorConfig(max_retries=2, retry_delay_base=0.25)
    )
    calls = []
    delays = []

    class Response:
        def raise_for_status(self):
            if len(calls) < 3:
                raise requests.exceptions.ConnectionError("service unavailable")

        def json(self):
            return {"response": "[]"}

    def post(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr(extractor.session, "post", post)
    monkeypatch.setattr("src.ingestor.triple_extractor.time.sleep", delays.append)

    assert extractor._call_ollama_with_retry("prompt") == {"response": "[]"}
    assert len(calls) == 3
    assert delays == [0.25, 0.5]


def test_shacl_runtime_failure_quarantines_candidate():
    """A validator runtime error is recoverable and blocks approval."""
    validator = SHACLValidator()
    validator._shacl_validation = lambda triples: (
        False,
        ["SHACL validation error: malformed RDF node"],
    )

    status, messages = validator.validate_and_classify(_triple())

    assert status == "quarantined"
    assert any("malformed RDF node" in message for message in messages)
    assert validator.health_check()["component"] == "shacl_validator"


def test_staging_corruption_is_backed_up_and_reinitialized(tmp_path: Path):
    """Invalid JSON is moved aside and does not prevent manager startup."""
    staging = tmp_path / "staging"
    staging.mkdir()
    corrupt = staging / "broken.json"
    corrupt.write_text("{ definitely not json", encoding="utf-8")

    manager = StagingManager(staging_path=staging, approved_kg_path=tmp_path / "approved.ttl")

    assert manager.staging_triples == {}
    assert not corrupt.exists()
    assert list(staging.glob("broken.corrupt.*.json"))
    assert manager.health_check()["component"] == "staging_manager"


def test_approval_rolls_back_when_merge_fails(tmp_path: Path, monkeypatch):
    """Approval failure leaves the staged record and graph unchanged."""
    manager = StagingManager(staging_path=tmp_path / "staging", approved_kg_path=tmp_path / "approved.ttl")
    record_id = manager.add_triple_for_staging(_triple(), ValidationStatus.QUARANTINED, ["review"])
    monkeypatch.setattr(manager, "_merge_into_approved_kg", lambda triple: (_ for _ in ()).throw(OSError("disk full")))

    assert manager.approve_triple(record_id, "reviewer") is False
    assert manager.staging_triples[record_id].approval_status is None
    assert not manager.approved_kg_path.exists()


def test_pipeline_checkpoint_recovery_and_component_health(tmp_path: Path):
    """Checkpoint state survives interruption and health covers all components."""
    pipeline = object.__new__(IngestionPipeline)
    pipeline.checkpoint_path = tmp_path / "checkpoint.json"
    pipeline.status = PipelineStatus.IN_PROGRESS
    pipeline._save_checkpoint({"document_key": "doc", "processed_chunks": ["chunk-1"]})

    assert pipeline.recover_interrupted_process()["processed_chunks"] == ["chunk-1"]

    class Healthy:
        def health_check(self):
            return {"status": "healthy"}

    for name in ("pdf_parser", "entity_extractor", "triple_extractor", "shacl_validator", "staging_manager", "vector_store"):
        setattr(pipeline, name, Healthy())
    health = pipeline.health_check()

    assert health["component"] == "ingestion_pipeline"
    assert set(health["components"]) == {
        "pdf_parser", "entity_extractor", "triple_extractor", "shacl_validator", "staging_manager", "vector_store"
    }


def test_default_ollama_timeout_allows_cold_generation_without_retry(monkeypatch):
    """A 42-second valid generation exposes the unfixed 30-second timeout and retries."""
    extractor = TripleExtractor()
    calls = []
    completion_seconds = 42.0

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "[]"}

    def post(*args, **kwargs):
        timeout = kwargs["timeout"]
        calls.append(timeout)
        if completion_seconds > timeout:
            raise requests.exceptions.Timeout(
                f"simulated read timeout={timeout}; completion={completion_seconds}"
            )
        return Response()

    monkeypatch.setattr(extractor.session, "post", post)
    monkeypatch.setattr("src.ingestor.triple_extractor.time.sleep", lambda _: None)

    failure = None
    result = None
    try:
        result = extractor._call_ollama_with_retry("cold-generation")
    except Exception as error:  # Capture the unfixed retry counterexample for the assertion.
        failure = error

    assert failure is None, (
        "Counterexample on unfixed code: a valid 42.0-second generation received "
        f"timeout values {calls!r}, retried {len(calls)} times, and failed with {failure!r}."
    )
    assert result == {"response": "[]"}
    assert calls == [120.0]


def test_explicit_timeout_precedes_environment_and_keeps_validation(monkeypatch):
    """Explicit timeout values remain authoritative and bounded."""
    monkeypatch.setenv("OLLAMA_TIMEOUT", "75.5")

    assert TripleExtractorConfig(timeout_seconds=15.0).timeout_seconds == 15.0

    with pytest.raises(ValidationError):
        TripleExtractorConfig(timeout_seconds=4.9)
    with pytest.raises(ValidationError):
        TripleExtractorConfig(timeout_seconds=120.1)


def test_transient_failures_exhaust_retries_and_report_last_error(monkeypatch):
    """Exhausted transient failures preserve attempts, backoff, and error state."""
    extractor = TripleExtractor(
        TripleExtractorConfig(max_retries=2, retry_delay_base=0.25)
    )
    calls = []
    delays = []

    def post(*args, **kwargs):
        del args, kwargs
        calls.append(1)
        raise requests.exceptions.ConnectionError("transient outage")

    monkeypatch.setattr(extractor.session, "post", post)
    monkeypatch.setattr("src.ingestor.triple_extractor.time.sleep", delays.append)

    with pytest.raises(TripleExtractorError, match="after 3 attempts"):
        extractor._call_ollama_with_retry("prompt")

    assert len(calls) == 3
    assert delays == [0.25, 0.5]
    assert extractor.last_error == "transient outage"


def test_extraction_failure_keeps_fallback_triples_and_last_error(monkeypatch):
    """A failed Ollama extraction still returns the existing fallback relationship."""
    extractor = TripleExtractor(TripleExtractorConfig(max_retries=0))
    error = TripleExtractorError("Ollama unavailable")
    monkeypatch.setattr(
        extractor,
        "_call_ollama_with_retry",
        lambda prompt: (_ for _ in ()).throw(error),
    )
    chunk = PDFChunk(
        id="fallback-chunk",
        text="Bank and HKMA are mentioned together.",
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={},
        start_char=0,
        end_char=36,
        document_id="doc",
        document_name="source.pdf",
    )
    entities = [
        SimpleNamespace(
            text="Bank",
            normalized_text="bank",
            entity_type="ORG",
        ),
        SimpleNamespace(
            text="HKMA",
            normalized_text="hkma",
            entity_type="ORG",
        ),
    ]

    triples, status = extractor.extract_triples_from_chunk(chunk, entities)

    assert status == ExtractionStatus.FAILED
    assert len(triples) == 1
    assert triples[0].predicate == extractor.config.fallback_predicate
    assert triples[0].metadata["fallback_type"] == "entity_relation"
    assert extractor.last_error == str(error)
    assert len(extractor.pending_extractions) == 1


def test_extraction_preserves_evidence_confidence_canonicalization_and_limit(monkeypatch):
    """Successful extraction retains validation, canonicalization, filtering, and limits."""
    source = "The bank must maintain capital requirements."
    response = {
        "response": json.dumps(
            [
                {
                    "subject": "Bank",
                    "predicate": "hasRequirement",
                    "object": "Capital",
                    "evidence": source,
                    "confidence": 0.9,
                },
                {
                    "subject": "Bank",
                    "predicate": "hasRequirement",
                    "object": "Liquidity",
                    "evidence": source,
                    "confidence": 0.8,
                },
                {
                    "subject": "Bank",
                    "predicate": "hasRequirement",
                    "object": "Reserve",
                    "evidence": source,
                    "confidence": 0.4,
                },
            ]
        )
    }
    extractor = TripleExtractor(
        TripleExtractorConfig(confidence_threshold=0.5, max_triples_per_chunk=1)
    )
    monkeypatch.setattr(extractor, "_call_ollama_with_retry", lambda prompt: response)
    chunk = PDFChunk(
        id="parse-chunk",
        text=source,
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={},
        start_char=0,
        end_char=len(source),
        document_id="doc",
        document_name="source.pdf",
    )

    triples, status = extractor.extract_triples_from_chunk(chunk)

    assert status == ExtractionStatus.SUCCESS
    assert len(triples) == 1
    assert triples[0].confidence == 0.9
    assert triples[0].subject == "finance:Bank"
    assert triples[0].predicate == "chimera:hasRequirement"
    assert triples[0].object == "chimera:Capital"
    assert triples[0].evidence == source
