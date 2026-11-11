"""Tests for HKMA/ART compliance controls."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.compliance import (
    AirGapVerifier,
    ComplianceAuditTrail,
    ComplianceError,
    DeterministicGuardrails,
    RetrievalTransparency,
    SurgeonsTableWorkflow,
)


@dataclass
class Triple:
    """Minimal extraction candidate used by deterministic tests."""

    subject: str = "chimera:Bank"
    predicate: str = "chimera:hasRequirement"
    object: str = "8 percent"
    evidence: str = "The bank must maintain 8 percent capital."
    confidence: float = 0.9
    chunk_id: str = "chunk-1"
    metadata: dict = None

    def __post_init__(self):
        self.metadata = self.metadata or {"document_id": "basel.pdf", "page_number": 4}


def test_air_gap_verifier_accepts_local_first_configuration(tmp_path: Path):
    report = AirGapVerifier(
        vector_store_path=tmp_path / "vectors",
        embedding_model="all-MiniLM-L6-v2",
    ).verify()

    assert report.compliant is True
    assert report.violations == []
    assert all(report.checks.values())


def test_air_gap_verifier_rejects_external_boundaries(tmp_path: Path):
    report = AirGapVerifier(
        ollama_base_url="https://llm.example.test",
        sparql_endpoint="https://sparql.example.test/query",
        vector_store_path="https://vectors.example.test",
        embedding_model="https://models.example.test/model",
        external_endpoints=["https://telemetry.example.test"],
    ).verify()

    assert report.compliant is False
    assert "ollama_loopback" in report.violations
    assert "sparql_local_or_disabled" in report.violations
    assert "vector_store_local" in report.violations
    assert "embedding_model_local" in report.violations
    assert "no_external_endpoints" in report.violations
    with pytest.raises(ComplianceError):
        AirGapVerifier(ollama_base_url="https://llm.example.test").assert_compliant()


def test_guardrails_reject_ungrounded_evidence():
    result = DeterministicGuardrails().evaluate(
        Triple(evidence="This sentence is absent."),
        "The source contains a different statement.",
    )

    assert result.allowed is False
    assert result.evidence_grounded is False
    assert any("substring" in message for message in result.messages)


def test_guardrails_are_case_insensitive_and_deterministic():
    guardrails = DeterministicGuardrails()
    candidate = Triple(evidence="THE BANK MUST MAINTAIN 8 PERCENT CAPITAL.")
    first = guardrails.evaluate(candidate, "The bank must maintain 8 percent capital.")
    second = guardrails.evaluate(candidate, "The bank must maintain 8 percent capital.")

    assert first.allowed is True
    assert first == second


def test_guardrail_test_report_detects_expected_effectiveness():
    report = DeterministicGuardrails().run_tests(
        [
            {"triple": Triple(), "source_text": "The bank must maintain 8 percent capital.", "expected_allowed": True},
            {"triple": Triple(evidence="not in source"), "source_text": "The bank must maintain 8 percent capital.", "expected_allowed": False},
        ]
    )

    assert report.effective is True
    assert report.total == report.passed == 2


def test_audit_trail_records_complete_hash_chain_and_decisions(tmp_path: Path):
    trail = ComplianceAuditTrail(tmp_path / "audit.jsonl")
    trail.record_extraction_decision(Triple(), decision="staged")
    trail.record_human_decision("record-1", "Compliance Officer (Demo)", "approved", reason="Reviewed source")
    trail.record_interaction("Risk Auditor", "opened_provenance", resource_id="record-1")

    complete, errors = trail.verify_completeness()
    assert complete is True
    assert errors == []
    assert len(trail.read()) == 3
    assert trail.read()[1]["details"]["human_attributed"] is True


def test_audit_trail_detects_tampering(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    trail = ComplianceAuditTrail(path)
    trail.record_interaction("Risk Auditor", "viewed_record")
    contents = path.read_text(encoding="utf-8").replace("viewed_record", "deleted_record")
    path.write_text(contents, encoding="utf-8")

    valid, errors = trail.verify_integrity()
    assert valid is False
    assert errors


def test_audit_trail_requires_human_attribution(tmp_path: Path):
    trail = ComplianceAuditTrail(tmp_path / "audit.jsonl")
    with pytest.raises(ComplianceError):
        trail.record_human_decision("record-1", "auto_approval", "approved")


def test_surgeons_table_blocks_automated_publication():
    workflow = SurgeonsTableWorkflow()
    row = {
        "Subject": "chimera:Bank",
        "Predicate": "chimera:hasRequirement",
        "Object": "8 percent",
        "Evidence Quote": "The bank must maintain 8 percent capital.",
        "SHACL Status": "VALID",
        "Approval Status": "APPROVED",
        "reviewed_by": "auto_approval",
    }

    issues = workflow.validate_record(row)
    assert any("human attribution" in issue for issue in issues)
    assert workflow.can_publish(row, "auto_approval") is False


def test_surgeons_table_requires_reason_for_quarantined_record():
    workflow = SurgeonsTableWorkflow()
    row = {
        "Subject": "chimera:Bank",
        "Predicate": "chimera:hasRequirement",
        "Object": "8 percent",
        "Evidence Quote": "The bank must maintain 8 percent capital.",
        "SHACL Status": "QUARANTINED",
        "Approval Status": "PENDING",
    }

    assert workflow.can_publish(row, "Risk Auditor") is False
    assert workflow.can_publish(row, "Risk Auditor", reason="Reviewed low confidence") is True


def test_retrieval_transparency_reports_both_contributions():
    report = RetrievalTransparency.report(
        0.75,
        [{"score": 0.8}],
        [{"score": 0.6}, {"score": 0.4}],
    )

    assert report["graph_weight"] == 0.75
    assert report["vector_weight"] == 0.25
    assert report["graph_result_count"] == 1
    assert report["vector_result_count"] == 2
    assert report["graph_contribution"] == pytest.approx(0.6)
    assert report["vector_contribution"] == pytest.approx(0.25)


def test_compliance_staging_keeps_valid_candidate_pending_until_human_review(tmp_path: Path):
    from datetime import datetime
    from src.ingestor.pipeline import ValidationStatus
    from src.ingestor.triple_extractor import ExtractedTriple
    from src.staging_manager import StagingManager

    manager = StagingManager(
        staging_path=tmp_path / "staging",
        approved_kg_path=tmp_path / "approved.ttl",
        require_human_approval=True,
    )
    triple = ExtractedTriple(
        subject="chimera:Bank",
        predicate="chimera:hasRequirement",
        object="8 percent",
        evidence="The bank must maintain 8 percent capital.",
        confidence=0.9,
        chunk_id="chunk-1",
        entity_anchors=["Bank"],
        metadata={"document_id": "basel.pdf", "page_number": 4},
        extraction_timestamp=datetime.now(),
    )
    record_id = manager.add_triple_for_staging(triple, ValidationStatus.VALID, ["valid"])

    assert manager.staging_triples[record_id].approval_status is None
    assert not (tmp_path / "approved.ttl").exists()
    assert manager.approve_triple(record_id, reviewer="Compliance Officer (Demo)") is True
    assert manager.staging_triples[record_id].reviewed_by == "Compliance Officer (Demo)"
