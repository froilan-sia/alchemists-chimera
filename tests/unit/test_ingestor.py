"""Unit and property tests for the PDF-to-RDF ingestion components."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("pydantic")
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st

from src.ingestor.pdf_parser import PDFChunk, PDFParser, PDFParserConfig, PDFParserError
from src.ingestor.pipeline import IngestionPipeline
from src.ingestor.shacl_validator import SHACLValidator
from src.ingestor.triple_extractor import (
    ExtractedTriple,
    TripleExtractor,
    TripleExtractorConfig,
)


@pytest.fixture
def triple_factory():
    """Create extracted triples with valid defaults for focused unit tests."""

    def make_triple(**overrides):
        values = {
            "subject": "chimera:Bank",
            "predicate": "chimera:hasRequirement",
            "object": "chimera:Capital",
            "evidence": "The bank must maintain capital requirements.",
            "confidence": 0.9,
            "chunk_id": "chunk-1",
            "entity_anchors": ["Bank"],
            "metadata": {"document_id": "sample.pdf", "page_number": 1},
            "extraction_timestamp": datetime.now(),
        }
        values.update(overrides)
        return ExtractedTriple(**values)

    return make_triple


def test_pdf_parser_splits_pages_with_configured_chunk_size():
    """Chunks have bounded size, stable IDs, and page metadata."""
    parser = PDFParser(PDFParserConfig(chunk_size=100, chunk_overlap=20))
    page_text = " ".join(["Banking regulation requires adequate capital."] * 12)
    reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: page_text)])

    chunks = parser._process_page(reader, 0, "document-1", "sample.pdf", 1)

    assert len(chunks) > 1
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.page_number == 1 for chunk in chunks)
    assert all(chunk.document_name == "sample.pdf" for chunk in chunks)
    assert all(chunk.total_chunks == len(chunks) for chunk in chunks)


def test_pdf_parser_raises_for_missing_file(tmp_path: Path):
    """Missing documents produce a clear file-not-found error."""
    parser = PDFParser()

    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        parser.parse_pdf(tmp_path / "missing.pdf")


def test_pdf_parser_wraps_corrupt_pdf_errors(tmp_path: Path):
    """Unreadable PDF bytes are exposed as the parser's domain error."""
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"not a PDF")

    with pytest.raises(PDFParserError, match="Failed to parse PDF"):
        PDFParser().parse_pdf(corrupt_pdf)


def test_triple_extractor_accepts_case_insensitive_verbatim_evidence():
    """Evidence validation accepts only a sufficiently long source substring."""
    extractor = TripleExtractor(TripleExtractorConfig(min_evidence_length=10))

    assert extractor._validate_evidence(
        "THE BANK MUST MAINTAIN CAPITAL.",
        "The bank must maintain capital.",
    )
    assert not extractor._validate_evidence(
        "not present in source", "A different statement."
    )
    assert not extractor._validate_evidence("too short", "too short in the source")


def test_triple_response_filters_ungrounded_evidence(triple_factory):
    """LLM responses with non-verbatim evidence never become extracted triples."""
    extractor = TripleExtractor(TripleExtractorConfig(min_evidence_length=10))
    response = {
        "response": (
            '[{"subject": "Bank", "predicate": "hasRequirement", '
            '"object": "Capital", "evidence": "The bank must maintain capital requirements.", '
            '"confidence": 0.9}, '
            '{"subject": "Bank", "predicate": "hasRequirement", '
            '"object": "Liquidity", "evidence": "This claim is absent from source.", '
            '"confidence": 0.9}]'
        )
    }

    triples = extractor._parse_and_validate_response(
        response,
        "chunk-1",
        "The bank must maintain capital requirements.",
        ["bank_org"],
    )

    assert len(triples) == 1
    assert (
        triples[0].evidence.lower()
        in "the bank must maintain capital requirements.".lower()
    )
    assert triples[0].subject.startswith("chimera:")
    assert triples[0].predicate.startswith("chimera:")
    assert triples[0].object.startswith("chimera:")


def test_shacl_validator_quarantines_low_confidence_triples(triple_factory):
    """Structurally valid but low-confidence triples require human review."""
    validator = SHACLValidator()
    status, messages = validator.validate_and_classify(triple_factory(confidence=0.2))

    assert status == "quarantined"
    assert any("Low confidence" in message for message in messages)


def test_shacl_validator_quarantines_short_evidence(triple_factory):
    """Evidence that passes the minimum structural length can still be quarantined."""
    validator = SHACLValidator()
    status, messages = validator.validate_and_classify(
        triple_factory(evidence="Evidence is short")
    )

    assert status == "quarantined"
    assert any("Short evidence" in message for message in messages)


def test_shacl_validator_rejects_malformed_triples(triple_factory):
    """Missing required fields are invalid rather than eligible for approval."""
    validator = SHACLValidator()
    status, messages = validator.validate_and_classify(triple_factory(subject=""))

    assert status == "invalid"
    assert any("subject" in message.lower() for message in messages)


@given(
    evidence=st.from_regex(r"[A-Za-z0-9][A-Za-z0-9 ]{8,78}[A-Za-z0-9]", fullmatch=True),
    prefix=st.from_regex(r"[A-Za-z ]{0,20}", fullmatch=True),
    suffix=st.from_regex(r"[A-Za-z ]{0,20}", fullmatch=True),
)
def test_evidence_grounding_accepts_case_insensitive_source_substrings(
    evidence: str, prefix: str, suffix: str
):
    """Property: a case variant of every source substring is grounded."""
    pipeline = object.__new__(IngestionPipeline)
    source = f"{prefix}{evidence}{suffix}"
    candidate = ExtractedTriple(
        subject="chimera:Bank",
        predicate="chimera:relatedTo",
        object="chimera:Capital",
        evidence=evidence.upper(),
        confidence=0.8,
        chunk_id="property-chunk",
        entity_anchors=["Bank"],
        metadata={},
    )

    assert pipeline._verify_evidence_grounding(candidate, source) is True


def test_evidence_grounding_rejects_absent_quotes(triple_factory):
    """The pipeline's deterministic gate rejects absent evidence quotes."""
    pipeline = object.__new__(IngestionPipeline)
    candidate = triple_factory(evidence="A statement absent from source.")

    assert (
        pipeline._verify_evidence_grounding(
            candidate, "The source says something else entirely."
        )
        is False
    )


def test_pipeline_metrics_are_safe_for_empty_and_partial_runs():
    """Metrics expose stable ratios and duration defaults before processing."""
    from src.ingestor.pipeline import PipelineMetrics

    metrics = PipelineMetrics()

    assert metrics.success_rate == 0.0
    assert metrics.validation_rate == 0.0
    assert metrics.duration_seconds == 0.0


def test_pdf_chunk_model_contains_ingestion_metadata():
    """The chunk contract carries source and positional metadata for provenance."""
    chunk = PDFChunk(
        id="doc-page001-chunk000",
        text="Source text",
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={"document_id": "doc"},
        start_char=0,
        end_char=11,
        document_id="doc",
        document_name="source.pdf",
    )

    assert chunk.metadata["document_id"] == "doc"
    assert chunk.page_number == 1
    assert chunk.document_name == "source.pdf"


def test_entity_extractor_filters_types_and_deduplicates(monkeypatch):
    """spaCy entities are filtered to configured types and deduplicated."""
    import spacy

    from src.ingestor.entity_extractor import EntityExtractor, EntityExtractorConfig

    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns(
        [
            {"label": "ORG", "pattern": "Bank of America"},
            {"label": "GPE", "pattern": "Hong Kong"},
            {"label": "DATE", "pattern": "2025"},
        ]
    )
    monkeypatch.setattr("src.ingestor.entity_extractor.spacy.load", lambda _: nlp)
    extractor = EntityExtractor(
        EntityExtractorConfig(entity_types=["ORG", "GPE"], min_confidence=0.0)
    )

    entities = extractor.extract_entities(
        "Bank of America operates in Hong Kong. Bank of America reported results in 2025."
    )

    assert {entity.entity_type for entity in entities} == {"ORG", "GPE"}
    assert len([entity for entity in entities if entity.entity_type == "ORG"]) == 1
    assert all(0.0 <= entity.confidence <= 1.0 for entity in entities)
    assert all("[" in entity.context for entity in entities)


def test_entity_extractor_handles_empty_text_and_statistics(monkeypatch):
    """Empty input is safe and distribution statistics remain deterministic."""
    import spacy

    from src.ingestor.entity_extractor import EntityExtractor, EntityExtractorConfig

    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "ORG", "pattern": "HKMA"}])
    monkeypatch.setattr("src.ingestor.entity_extractor.spacy.load", lambda _: nlp)
    extractor = EntityExtractor(EntityExtractorConfig(min_confidence=0.0))

    assert extractor.extract_entities("   ") == []
    stats = extractor.get_entity_statistics("HKMA issued guidance.")

    assert stats["total_entities"] == 1
    assert stats["entity_distribution"] == {"ORG": 1}
    assert stats["min_confidence"] <= stats["average_confidence"]


def test_triple_extractor_serializes_and_prepares_anchor_data(triple_factory):
    """Prompt, anchor, cleanup, and serialization helpers preserve contracts."""
    from src.ingestor.entity_extractor import ExtractedEntity

    extractor = TripleExtractor(TripleExtractorConfig())
    entities = [
        ExtractedEntity(
            text="Bank of America",
            entity_type="ORG",
            start_char=0,
            end_char=15,
            confidence=0.9,
            context="[Bank of America] reported results",
            normalized_text="bank of america",
            metadata={},
        )
    ]
    anchors = extractor._prepare_entity_anchors(entities)
    triple = triple_factory(subject="chimera:bank_of_america")

    assert anchors == ["bank of america_org"]
    assert extractor._find_entity_anchors(
        "chimera:bank of america", "chimera:capital", ["bank of america"]
    ) == ["bank of america"]
    assert "bank of america_org" in extractor._generate_extraction_prompt(
        "source", anchors
    )
    assert extractor._clean_response_text("```json\n[]\n```") == "[]"
    assert "chimera:bank_of_america" in triple.to_turtle()
    assert triple.to_json()["evidence"] == triple.evidence


def test_triple_extractor_creates_fallback_relationships():
    """Fallback extraction links available entities with the configured predicate."""
    from src.ingestor.entity_extractor import ExtractedEntity

    extractor = TripleExtractor(TripleExtractorConfig())
    entities = [
        ExtractedEntity("Bank", "ORG", 0, 4, 0.9, "[Bank]", "bank", {}),
        ExtractedEntity("HKMA", "ORG", 9, 13, 0.9, "[HKMA]", "hkma", {}),
    ]
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

    triples = extractor._create_fallback_triples(chunk, entities)

    assert triples
    assert triples[0].predicate == "chimera:relatedTo"
    assert triples[0].chunk_id == chunk.id


def test_provenance_manager_normalizes_labels_and_serializes_records(
    triple_factory, tmp_path: Path
):
    """Provenance URIs are safe while original text remains in RDF labels."""
    from src.ingestor.provenance_manager import ProvenanceManager

    manager = ProvenanceManager()
    triple = triple_factory(
        subject="Bank of America",
        predicate="has capital requirement",
        object="Basel III",
    )
    chunk = PDFChunk(
        id="chunk-1",
        text=triple.evidence,
        page_number=4,
        chunk_index=0,
        total_chunks=1,
        metadata={},
        start_char=0,
        end_char=len(triple.evidence),
        document_id="doc-1",
        document_name="basel.pdf",
    )

    record = manager.create_provenance_record(triple, chunk)
    graph = manager.create_provenance_graph([record], {chunk.id: chunk})
    output = tmp_path / "provenance.ttl"
    turtle = manager.serialize_provenance_to_turtle(graph, output)

    assert record.document_id == "doc-1"
    assert record.page_number == 4
    assert " " not in record.subject_uri
    assert "Bank of America" in turtle
    assert output.exists()
    assert manager.validate_provenance_chain([record])[0].value == "success"


def test_provenance_manager_detects_duplicate_and_invalid_records(triple_factory):
    """Chain validation reports duplicate identifiers and invalid confidence."""
    from src.ingestor.provenance_manager import ProvenanceManager, ProvenanceRecord

    manager = ProvenanceManager()
    record = manager.create_provenance_record(triple_factory())
    invalid = ProvenanceRecord(
        triple_uri=record.triple_uri,
        subject_uri=record.subject_uri,
        predicate_uri=record.predicate_uri,
        object_uri=record.object_uri,
        original_subject=record.original_subject,
        original_predicate=record.original_predicate,
        original_object=record.original_object,
        evidence=record.evidence,
        confidence=2.0,
        chunk_id=record.chunk_id,
    )

    status, messages = manager.validate_provenance_chain([record, invalid])

    assert status.value == "invalid"
    assert any("duplicate" in message.lower() for message in messages)
    assert any("confidence" in message.lower() for message in messages)


def test_provenance_manager_batch_and_export(tmp_path: Path, triple_factory):
    """Batch provenance processing skips failed chunks and exports all formats."""
    from src.ingestor.provenance_manager import ProvenanceManager
    from src.ingestor.triple_extractor import ExtractionStatus

    manager = ProvenanceManager()
    chunk = PDFChunk(
        id="chunk-1",
        text="The bank must maintain capital requirements.",
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={},
        start_char=0,
        end_char=45,
        document_id="doc-1",
        document_name="source.pdf",
    )
    records, status = manager.batch_process_triples(
        {
            "chunk-1": ([triple_factory()], ExtractionStatus.SUCCESS),
            "failed": ([], ExtractionStatus.FAILED),
        },
        {"chunk-1": chunk},
    )
    files = manager.export_provenance_package(records, {"chunk-1": chunk}, tmp_path)

    assert status.value == "success"
    assert len(records) == 1
    assert {"turtle", "jsonld", "rdfxml", "summary"} == set(files)
    assert all(path.exists() for path in files.values())


def test_shacl_validation_report_classifies_valid_and_quarantined(triple_factory):
    """Validation reports expose counts for valid, quarantined, and invalid data."""
    validator = SHACLValidator()
    triples = [
        triple_factory(confidence=0.9),
        triple_factory(confidence=0.2, chunk_id="low-confidence"),
        triple_factory(subject="", chunk_id="invalid"),
    ]

    report = validator.create_validation_report(triples)

    assert report["total_triples"] == 3
    assert set(report["classifications"]) == {"valid", "quarantined", "invalid"}
    assert sum(report["classifications"].values()) == 3
