"""Regression checks for Task 21 repository cleanup and approval wording."""

from datetime import datetime
from pathlib import Path

from src.ingestor.pipeline import StagingRecord, ValidationStatus
from src.ingestor.staging_adapter import get_staging_manager
from src.ingestor.triple_extractor import ExtractedTriple


REPOSITORY_ROOT = Path(__file__).parents[1]


def _valid_triple() -> ExtractedTriple:
    """Create a grounded, structurally valid candidate for staging checks."""
    return ExtractedTriple(
        subject="chimera:Bank",
        predicate="chimera:hasRequirement",
        object="chimera:Capital",
        evidence="The bank must maintain capital requirements.",
        confidence=0.9,
        chunk_id="task21-chunk",
        entity_anchors=["Bank"],
        metadata={"document_id": "task21.pdf", "page_number": 1},
        extraction_timestamp=datetime.now(),
    )


def test_default_pipeline_stages_valid_records_until_human_approval(
    tmp_path: Path, monkeypatch
):
    """The default adapter keeps VALID records pending and out of the live graph."""
    monkeypatch.chdir(tmp_path)
    manager = get_staging_manager(Path("data/staging"), use_comprehensive=True)
    record = StagingRecord(
        triple=_valid_triple(),
        validation_status=ValidationStatus.VALID,
        validation_messages=["validation passed"],
        provenance_record=None,
    )

    record_id = manager.add_record(record)
    backend = manager.comprehensive_manager
    staged = backend.staging_triples[record_id]

    assert backend.require_human_approval is True
    assert staged.approval_status is None
    assert staged.reviewed_by is None
    assert any(pending_id == record_id for pending_id, _ in backend.get_pending_review())
    assert not (tmp_path / "data" / "knowledge_graph.ttl").exists()


def test_readme_describes_default_and_legacy_approval_paths():
    """README approval claims match the default adapter and legacy direct mode."""
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    normalized = readme.lower()

    assert "default ingestion pipeline keeps `valid` records pending" in normalized
    assert "current backend auto-merges `valid` records" not in normalized
    assert "require_human_approval=false" in normalized
    assert "require_human_approval=true" in normalized
