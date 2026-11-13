"""Bug-condition exploration tests for the staging adapter approval flag.

These tests intentionally target the current unfixed implementation.  The
explicit-flag properties and the Surgeon’s Table startup seam are expected to
fail until the adapter constructor accepts and forwards the approval setting.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src import staging_manager as staging_manager_module
from src.ingestor import pipeline
from src.ingestor import staging_adapter
from src.ingestor.pipeline import StagingRecord, ValidationStatus
from src.ingestor.staging_adapter import (
    CompatibleStagingManager,
    get_staging_manager,
)
from src.ingestor.triple_extractor import ExtractedTriple
from src.staging_manager import ApprovalDecision, StagingManager as ComprehensiveStagingManager


@pytest.mark.parametrize(
    "constructor_path",
    [
        "CompatibleStagingManager",
        "src.ingestor.staging_adapter.StagingManager",
    ],
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(requested_flag=st.booleans())
def test_approval_flag_is_accepted_by_both_adapter_entry_points(
    tmp_path: Path,
    constructor_path: str,
    requested_flag: bool,
):
    """The adapter should accept every boolean through either public entry point."""
    constructors: dict[str, Callable[..., CompatibleStagingManager]] = {
        "CompatibleStagingManager": CompatibleStagingManager,
        "src.ingestor.staging_adapter.StagingManager": staging_adapter.StagingManager,
    }
    constructor = constructors[constructor_path]
    staging_path = tmp_path / constructor_path.rsplit(".", maxsplit=1)[-1]

    result = constructor(
        staging_path,
        require_human_approval=requested_flag,
    )

    assert isinstance(result, CompatibleStagingManager)
    assert result.comprehensive_manager.require_human_approval is requested_flag


def test_surgeons_table_pipeline_factory_reaches_staging_startup_regression(
    tmp_path: Path,
):
    """The Surgeon’s Table factory seam fails before staging on the unfixed adapter."""

    class StartupPipeline:
        """Lightweight pipeline double matching render_surgeons_table’s factory seam."""

        def __init__(self, staging_path: Path):
            self.staging_manager = staging_adapter.StagingManager(
                staging_path,
                require_human_approval=True,
            )

    def pipeline_factory(*, chunk_size: int, chunk_overlap: int) -> StartupPipeline:
        """Construct the staging dependency used during extraction startup."""
        assert chunk_size == 1000
        assert chunk_overlap == 200
        return StartupPipeline(tmp_path / "surgeons-staging")

    with pytest.raises(TypeError, match="require_human_approval"):
        pipeline_factory(chunk_size=1000, chunk_overlap=200)


@st.composite
def valid_staging_records(draw):
    """Generate structurally valid records for isolated staging tests."""
    subject = draw(st.sampled_from(["chimera:Bank", "chimera:Authority", "chimera:Fund"]))
    predicate = draw(st.sampled_from(["chimera:requires", "chimera:regulates"]))
    object_value = draw(st.sampled_from(["chimera:Capital", "chimera:Liquidity"]))
    evidence = draw(
        st.sampled_from(
            [
                "The bank must maintain capital requirements.",
                "The authority regulates liquidity requirements.",
            ]
        )
    )
    triple = ExtractedTriple(
        subject=subject,
        predicate=predicate,
        object=object_value,
        evidence=evidence,
        confidence=0.9,
        chunk_id=draw(st.integers(min_value=1, max_value=100_000)).__str__(),
        entity_anchors=[subject.rsplit(":", maxsplit=1)[-1]],
        metadata={"document_id": "generated.pdf", "page_number": 1},
        extraction_timestamp=datetime.now(),
    )
    return StagingRecord(
        triple=triple,
        validation_status=ValidationStatus.VALID,
        validation_messages=["validation passed"],
        provenance_record=None,
    )


def test_omitted_and_path_only_construction_preserve_adapter_default(
    tmp_path: Path, monkeypatch
):
    """Existing constructor forms retain the adapter's human-approval default."""
    monkeypatch.setattr(
        staging_manager_module,
        "settings",
        SimpleNamespace(
            staging_path=tmp_path / "default-staging",
            approved_kg_path=tmp_path / "default-approved.ttl",
        ),
    )

    omitted = CompatibleStagingManager()
    path_only = staging_adapter.StagingManager(tmp_path / "path-only")

    assert isinstance(omitted, CompatibleStagingManager)
    assert isinstance(path_only, CompatibleStagingManager)
    assert omitted.comprehensive_manager.require_human_approval is True
    assert path_only.comprehensive_manager.require_human_approval is True


def test_comprehensive_factory_preserves_adapter_contract(tmp_path: Path):
    """The comprehensive factory branch returns the compatibility adapter."""
    manager = get_staging_manager(tmp_path / "comprehensive", use_comprehensive=True)

    assert isinstance(manager, CompatibleStagingManager)
    assert manager.comprehensive_manager.require_human_approval is True


def test_legacy_factory_branch_selects_the_pipeline_manager(
    tmp_path: Path, monkeypatch
):
    """The false factory branch delegates to the legacy pipeline manager."""

    class LegacyPipelineManager:
        """Minimal legacy-manager sentinel for testing factory selection."""

        def __init__(self, staging_path: Path):
            self.staging_path = staging_path

    monkeypatch.setattr(pipeline, "StagingManager", LegacyPipelineManager, raising=False)

    manager = get_staging_manager(tmp_path / "legacy", use_comprehensive=False)

    assert isinstance(manager, LegacyPipelineManager)
    assert manager.staging_path == tmp_path / "legacy"


@settings(max_examples=8, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(record=valid_staging_records())
def test_generated_valid_records_remain_pending_with_adapter_default(
    tmp_path: Path, record: StagingRecord
):
    """Generated valid records retain pending status in the default adapter."""
    manager = CompatibleStagingManager(tmp_path / "adapter")
    record_id = manager.add_record(record)
    staged = manager.comprehensive_manager.staging_triples[record_id]

    assert staged.approval_status is None
    assert staged.reviewed_by is None
    assert any(pending_id == record_id for pending_id, _ in manager.comprehensive_manager.get_pending_review())


@settings(max_examples=8, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(requested_flag=st.booleans(), record=valid_staging_records())
def test_generated_valid_records_preserve_backend_approval_modes(
    tmp_path: Path, requested_flag: bool, record: StagingRecord
):
    """The existing comprehensive backend preserves both approval modes."""
    manager = ComprehensiveStagingManager(
        staging_path=tmp_path / f"backend-{requested_flag}",
        approved_kg_path=tmp_path / f"approved-{requested_flag}.ttl",
        require_human_approval=requested_flag,
    )
    record_id = manager.add_triple_for_staging(
        triple=record.triple,
        validation_status=record.validation_status,
        validation_messages=record.validation_messages,
    )
    staged = manager.staging_triples[record_id]

    if requested_flag:
        assert staged.approval_status is None
        assert any(pending_id == record_id for pending_id, _ in manager.get_pending_review())
    else:
        assert staged.approval_status is ApprovalDecision.APPROVED
        assert staged.reviewed_by == "auto_approval"
        assert any(approved_id == record_id for approved_id, _ in manager.get_approved_triples())
        assert all(pending_id != record_id for pending_id, _ in manager.get_pending_review())


def test_adapter_delegates_review_statistics_and_proxy_operations(
    tmp_path: Path, monkeypatch
):
    """Existing adapter methods continue delegating to the comprehensive backend."""
    monkeypatch.setattr(
        staging_manager_module,
        "settings",
        SimpleNamespace(approved_kg_path=tmp_path / "approved.ttl"),
    )
    manager = CompatibleStagingManager(tmp_path / "staging")
    record = StagingRecord(
        triple=ExtractedTriple(
            subject="chimera:Bank",
            predicate="chimera:requires",
            object="chimera:Capital",
            evidence="The bank must maintain capital requirements.",
            confidence=0.9,
            chunk_id="delegation-chunk",
            entity_anchors=["Bank"],
            metadata={"document_id": "delegation.pdf", "page_number": 1},
            extraction_timestamp=datetime.now(),
        ),
        validation_status=ValidationStatus.VALID,
        validation_messages=["validation passed"],
        provenance_record=None,
    )

    approved_id = manager.add_record(record)
    edited = manager.edit_triple(
        record_id=approved_id,
        editor="Risk Auditor",
        subject="chimera:ReviewedBank",
        evidence="The reviewed bank must maintain capital requirements.",
    )
    assert edited is not None
    assert manager.get_pending_review()[0].triple.subject == "chimera:ReviewedBank"
    assert manager.get_stats()["pending_review"] == 1
    assert manager.approve_triple(record_id=approved_id, reviewer="Compliance Officer") is True
    assert any(record_id == approved_id for record_id, _ in manager.get_approved_triples())

    rejected_id = manager.add_record(
        StagingRecord(
            triple=record.triple,
            validation_status=ValidationStatus.QUARANTINED,
            validation_messages=["needs review"],
            provenance_record=None,
        )
    )
    assert manager.mark_as_reviewed(
        rejected_id, "Compliance Officer", ValidationStatus.QUARANTINED
    ) is True
    assert any(record_id == rejected_id for record_id, _ in manager.get_rejected_triples())

    export_path = manager.export_approved_kg(tmp_path / "export.ttl")
    assert export_path == tmp_path / "export.ttl"
    assert export_path.exists()
    assert manager.reset_staging() == 1
    assert approved_id in manager.comprehensive_manager.staging_triples
