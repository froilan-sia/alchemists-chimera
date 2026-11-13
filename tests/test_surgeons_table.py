"""Focused tests for the Surgeon’s Table upload and HITL helpers."""

from datetime import datetime
from pathlib import Path

from components.surgeons_table import (
    apply_table_edits,
    approve_records,
    auto_approve_valid_records,
    filter_and_sort_rows,
    reject_records,
    save_uploaded_pdf,
    selected_record_ids,
    staging_table_rows,
)
from src.ingestor.pipeline import ValidationStatus
from src.ingestor.triple_extractor import ExtractedTriple
from src.staging_manager import ApprovalDecision, StagingManager


class UploadedFile:
    """Small UploadedFile-compatible object for upload integration tests."""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def make_manager(
    tmp_path: Path, require_human_approval: bool = False
) -> StagingManager:
    """Create an isolated staging manager for UI workflow tests."""
    return StagingManager(
        staging_path=tmp_path / "staging",
        approved_kg_path=tmp_path / "approved.ttl",
        require_human_approval=require_human_approval,
    )


def add_triple(manager: StagingManager, status: ValidationStatus) -> str:
    """Add a deterministic triple to an isolated staging manager."""
    triple = ExtractedTriple(
        subject="HKMA",
        predicate="chimera:requires",
        object="Capital Ratio",
        evidence="HKMA requires a capital ratio.",
        confidence=0.8,
        chunk_id="chunk-1",
        entity_anchors=["HKMA"],
        metadata={"validation_status": status.value},
        extraction_timestamp=datetime.now(),
    )
    return manager.add_triple_for_staging(triple, status, [status.value])


def test_save_uploaded_pdf_uses_safe_unique_path(tmp_path):
    """Uploaded PDFs are persisted without trusting the client filename."""
    path = save_uploaded_pdf(
        UploadedFile("../../regulatory policy 2026.pdf", b"%PDF-test"),
        tmp_path,
    )

    assert path.parent == tmp_path
    assert path.suffix == ".pdf"
    assert ".." not in path.name
    assert path.read_bytes() == b"%PDF-test"


def test_staging_table_rows_expose_required_columns_and_filter_sort(tmp_path):
    """The table model exposes HITL fields and supports status/text sorting."""
    manager = make_manager(tmp_path)
    quarantined_id = add_triple(manager, ValidationStatus.QUARANTINED)
    rows = staging_table_rows(manager)

    assert rows[0]["_record_id"] == quarantined_id
    assert rows[0]["SHACL Status"] == "QUARANTINED"
    assert {
        "Subject",
        "Predicate",
        "Object",
        "Evidence Quote",
        "SHACL Status",
    }.issubset(rows[0])

    rows[0]["Selected"] = True
    assert selected_record_ids(rows) == [quarantined_id]
    filtered = filter_and_sort_rows(rows, search_text="capital", status_filter="QUARANTINED")
    assert [row["_record_id"] for row in filtered] == [quarantined_id]


def test_edit_multiple_persists_values_before_approval(tmp_path):
    """Bulk table edits update the manager’s editable triple fields."""
    manager = make_manager(tmp_path)
    record_id = add_triple(manager, ValidationStatus.QUARANTINED)
    rows = staging_table_rows(manager)
    rows[0].update(
        {
            "Selected": True,
            "Subject": "HKMA Board",
            "Object": "8 percent capital ratio",
            "Evidence Quote": "HKMA requires an 8 percent capital ratio.",
        }
    )

    changed = apply_table_edits(manager, rows, reviewer="Risk Auditor")
    staging_triple = manager.staging_triples[record_id]

    assert changed == [record_id]
    assert staging_triple.subject == "HKMA Board"
    assert staging_triple.object == "8 percent capital ratio"
    assert staging_triple.triple.evidence == "HKMA requires an 8 percent capital ratio."


def test_bulk_rejection_records_reviewer_and_reason(tmp_path):
    """Rejecting selected rows delegates the audit reason to the manager."""
    manager = make_manager(tmp_path)
    record_id = add_triple(manager, ValidationStatus.QUARANTINED)

    rejected = reject_records(
        manager,
        [record_id],
        reviewer="Compliance Officer (Demo)",
        reason="Evidence requires manual verification.",
    )

    assert rejected == [record_id]
    record = manager.staging_triples[record_id]
    assert record.approval_status == ApprovalDecision.REJECTED
    assert record.reviewed_by == "Compliance Officer (Demo)"
    assert record.rejection_reason == "Evidence requires manual verification."


def test_auto_approval_targets_only_pending_valid_records(tmp_path):
    """The one-click action skips quarantined and already approved records."""
    manager = make_manager(tmp_path)
    valid_id = add_triple(manager, ValidationStatus.VALID)
    quarantined_id = add_triple(manager, ValidationStatus.QUARANTINED)

    # The current staging manager auto-approves VALID records at ingestion;
    # this assertion ensures the UI action remains idempotent and scoped.
    approved = auto_approve_valid_records(manager, reviewer="Compliance Officer (Demo)")

    assert approved == []
    assert manager.staging_triples[valid_id].approval_status == ApprovalDecision.APPROVED
    assert manager.staging_triples[quarantined_id].approval_status is None


def test_approval_and_auto_approval_helpers_preserve_isolated_manager_outcomes(
    tmp_path,
):
    """Approval helpers keep pending, approved, and quarantined outcomes distinct."""
    approval_manager = make_manager(
        tmp_path / "explicit-approval", require_human_approval=True
    )
    valid_id = add_triple(approval_manager, ValidationStatus.VALID)
    rows = staging_table_rows(approval_manager)
    rows[0]["Selected"] = True

    assert rows[0]["Approval Status"] == "PENDING"
    assert approve_records(
        approval_manager, selected_record_ids(rows), "Compliance Officer (Demo)"
    ) == [valid_id]
    assert approval_manager.staging_triples[valid_id].approval_status == ApprovalDecision.APPROVED

    auto_manager = make_manager(
        tmp_path / "explicit-auto", require_human_approval=True
    )
    auto_valid_id = add_triple(auto_manager, ValidationStatus.VALID)
    quarantined_id = add_triple(auto_manager, ValidationStatus.QUARANTINED)

    assert auto_approve_valid_records(
        auto_manager, reviewer="Compliance Officer (Demo)"
    ) == [auto_valid_id]
    assert auto_manager.staging_triples[auto_valid_id].approval_status == ApprovalDecision.APPROVED
    assert auto_manager.staging_triples[quarantined_id].approval_status is None
