"""HKMA GenAI Sandbox and ART Framework compliance controls.

The module contains deterministic, local-only controls around the existing
ingestion, staging, and hybrid retrieval components.  It deliberately uses
stdlib data structures so compliance checks remain available when optional
LLM or UI dependencies are unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
AUTOMATED_ACTORS = frozenset({"", "system", "auto_approval", "automated", "bot"})
APPROVED_DECISIONS = frozenset({"approved", "edited_and_approved"})


class ComplianceError(ValueError):
    """Base exception for a failed compliance control."""


@dataclass(frozen=True)
class AirGapReport:
    """Result of checking all configured runtime boundaries."""

    compliant: bool
    checks: Dict[str, bool]
    violations: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report."""
        return asdict(self)


class AirGapVerifier:
    """Verify that configured services can operate without external calls.

    The verifier checks configuration, not the physical network.  Deployments
    should run it at startup and keep the returned report with their audit
    package.  Only loopback Ollama and local filesystem stores are accepted.
    """

    def __init__(
        self,
        *,
        model_name: str = "qwen2.5:3b",
        ollama_base_url: str = "http://localhost:11434",
        sparql_endpoint: Optional[str] = None,
        vector_store_path: str | Path = "./data/vector_store",
        embedding_model: str = "all-MiniLM-L6-v2",
        external_endpoints: Optional[Iterable[str]] = None,
    ) -> None:
        self.model_name = model_name
        self.ollama_base_url = ollama_base_url
        self.sparql_endpoint = sparql_endpoint
        self.vector_store_path = str(vector_store_path)
        self.embedding_model = embedding_model
        self.external_endpoints = list(external_endpoints or [])

    @staticmethod
    def _is_local_endpoint(endpoint: Optional[str]) -> bool:
        """Return whether an endpoint is absent or points to loopback."""
        if endpoint is None or not str(endpoint).strip():
            return True
        parsed = urlparse(str(endpoint))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        return parsed.hostname.lower().strip("[]") in LOCAL_HOSTS

    @staticmethod
    def _is_local_model(model: str) -> bool:
        """Return whether an embedding model is a local path or known local ID."""
        if not model or model.startswith(("http://", "https://")):
            return False
        path = Path(model).expanduser()
        return path.exists() or model == "all-MiniLM-L6-v2"

    def verify(self) -> AirGapReport:
        """Check local model, endpoint, and storage configuration."""
        checks = {
            "ollama_loopback": self._is_local_endpoint(self.ollama_base_url),
            "ollama_model": self.model_name == "qwen2.5:3b",
            "sparql_local_or_disabled": self._is_local_endpoint(self.sparql_endpoint),
            "vector_store_local": not str(self.vector_store_path).lower().startswith(("http://", "https://")),
            "embedding_model_local": self._is_local_model(self.embedding_model),
            "no_external_endpoints": all(self._is_local_endpoint(value) for value in self.external_endpoints),
        }
        violations = [name for name, passed in checks.items() if not passed]
        return AirGapReport(compliant=not violations, checks=checks, violations=violations)

    def assert_compliant(self) -> AirGapReport:
        """Raise ``ComplianceError`` unless every air-gap check passes."""
        report = self.verify()
        if not report.compliant:
            raise ComplianceError("Air-gapped operation check failed: " + ", ".join(report.violations))
        return report

    @property
    def is_air_gapped(self) -> bool:
        """Return the current configuration's air-gap status."""
        return self.verify().compliant


class DeterministicGuardrails:
    """Apply evidence grounding and SHACL classification before publication."""

    def __init__(self, validator: Optional[Any] = None) -> None:
        self.validator = validator

    @staticmethod
    def _evidence(triple: Any) -> str:
        return str(getattr(triple, "evidence", getattr(triple, "evidence_quote", "")) or "").strip()

    @staticmethod
    def _basic_checks(triple: Any) -> List[str]:
        messages: List[str] = []
        for field_name in ("subject", "predicate", "object"):
            if not str(getattr(triple, field_name, "") or "").strip():
                messages.append(f"Missing {field_name}")
        confidence = getattr(triple, "confidence", None)
        if confidence is None or not 0.0 <= float(confidence) <= 1.0:
            messages.append("Confidence must be between 0 and 1")
        if not DeterministicGuardrails._evidence(triple):
            messages.append("Missing evidence")
        return messages

    def evaluate(self, triple: Any, source_text: str) -> "GuardrailResult":
        """Evaluate one candidate using deterministic checks only."""
        messages = self._basic_checks(triple)
        evidence = self._evidence(triple)
        grounded = bool(evidence) and evidence.casefold() in str(source_text).casefold()
        if not grounded:
            messages.append("Evidence quote is not a case-insensitive source substring")

        classification = "valid"
        if self.validator is not None and not messages:
            classification, validator_messages = self.validator.validate_and_classify(triple)
            messages.extend(str(message) for message in validator_messages)
        elif messages:
            classification = "invalid"

        allowed = not messages and classification == "valid"
        return GuardrailResult(
            allowed=allowed,
            evidence_grounded=grounded,
            validation_status=classification,
            messages=messages,
        )

    def assert_publishable(self, triple: Any, source_text: str) -> "GuardrailResult":
        """Raise unless a candidate is grounded and passes deterministic validation."""
        result = self.evaluate(triple, source_text)
        if not result.allowed:
            raise ComplianceError("Triple failed publication guardrails: " + "; ".join(result.messages))
        return result

    def run_tests(self, cases: Iterable[Mapping[str, Any]]) -> "GuardrailTestReport":
        """Run deterministic guardrail cases and report effectiveness.

        Each case contains ``triple``, ``source_text``, and ``expected_allowed``.
        """
        results: List[GuardrailResult] = []
        failures: List[str] = []
        for index, case in enumerate(cases):
            result = self.evaluate(case["triple"], str(case.get("source_text", "")))
            results.append(result)
            if result.allowed != bool(case.get("expected_allowed", False)):
                failures.append(f"case {index}: expected {case.get('expected_allowed')}, got {result.allowed}")
        return GuardrailTestReport(
            total=len(results),
            passed=len(results) - len(failures),
            failures=failures,
            results=results,
        )

    run_guardrail_tests = run_tests


@dataclass(frozen=True)
class GuardrailResult:
    """Deterministic outcome for one extraction candidate."""

    allowed: bool
    evidence_grounded: bool
    validation_status: str
    messages: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable result."""
        return asdict(self)


@dataclass(frozen=True)
class GuardrailTestReport:
    """Summary of deterministic guardrail test cases."""

    total: int
    passed: int
    failures: List[str]
    results: List[GuardrailResult]

    @property
    def effective(self) -> bool:
        """Whether every supplied test case produced the expected result."""
        return not self.failures


@dataclass(frozen=True)
class AuditEvent:
    """One hash-chained compliance event."""

    event_id: str
    event_type: str
    actor: str
    timestamp: str
    resource_id: Optional[str]
    details: Dict[str, Any]
    previous_hash: str
    event_hash: str


class ComplianceAuditTrail:
    """Append-only JSONL audit trail with tamper-evident hash chaining."""

    def __init__(self, path: str | Path = "data/audit/compliance_audit.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _events(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        events: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ComplianceError(f"Malformed audit event at line {line_number}") from error
        return events

    def record(
        self,
        event_type: str,
        actor: str,
        *,
        resource_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEvent:
        """Append an event and return its immutable representation."""
        if not event_type.strip():
            raise ComplianceError("Audit event type is required")
        if not actor.strip():
            raise ComplianceError("Audit actor is required")
        existing = self._events()
        previous_hash = existing[-1].get("event_hash", "") if existing else ""
        timestamp_value = (timestamp or datetime.now(timezone.utc)).isoformat()
        payload = {
            "event_id": uuid.uuid4().hex,
            "event_type": event_type,
            "actor": actor,
            "timestamp": timestamp_value,
            "resource_id": resource_id,
            "details": dict(details or {}),
            "previous_hash": previous_hash,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        payload["event_hash"] = hashlib.sha256(encoded).hexdigest()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return AuditEvent(**payload)

    def record_extraction_decision(
        self,
        triple: Any,
        *,
        decision: str,
        source_document: Optional[str] = None,
        page_number: Optional[int] = None,
        provenance_uri: Optional[str] = None,
        actor: str = "system",
        reason: str = "",
    ) -> AuditEvent:
        """Document an AI-assisted extraction decision and its source link."""
        metadata = dict(getattr(triple, "metadata", {}) or {})
        details = {
            "ai_assisted": True,
            "model": metadata.get("model", "qwen2.5:3b"),
            "subject": getattr(triple, "subject", ""),
            "predicate": getattr(triple, "predicate", ""),
            "object": getattr(triple, "object", ""),
            "evidence_quote": getattr(triple, "evidence", getattr(triple, "evidence_quote", "")),
            "chunk_id": getattr(triple, "chunk_id", None),
            "source_document": source_document or metadata.get("document_id"),
            "page_number": page_number if page_number is not None else metadata.get("page_number"),
            "provenance_uri": provenance_uri,
            "confidence": getattr(triple, "confidence", None),
            "decision": decision,
            "reason": reason,
        }
        return self.record("ai_extraction_decision", actor, resource_id=details["chunk_id"], details=details)

    def record_human_decision(
        self,
        record_id: str,
        reviewer: str,
        decision: str,
        *,
        reason: str = "",
        edited: bool = False,
    ) -> AuditEvent:
        """Record an attributed human approval, rejection, or edit."""
        if reviewer.strip().casefold() in AUTOMATED_ACTORS:
            raise ComplianceError("A human reviewer is required for a decision")
        if not decision.strip():
            raise ComplianceError("Human decision is required")
        return self.record(
            "human_staging_decision",
            reviewer,
            resource_id=record_id,
            details={"decision": decision, "reason": reason, "edited": edited, "human_attributed": True},
        )

    def record_interaction(self, actor: str, action: str, *, resource_id: Optional[str] = None, **details: Any) -> AuditEvent:
        """Record a user interaction for regulatory audit support."""
        return self.record("user_interaction", actor, resource_id=resource_id, details={"action": action, **details})

    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """Verify event hashes and previous-hash links from the beginning."""
        errors: List[str] = []
        previous_hash = ""
        for index, event in enumerate(self._events()):
            expected = event.get("event_hash", "")
            payload = {key: event.get(key) for key in (
                "event_id", "event_type", "actor", "timestamp", "resource_id", "details", "previous_hash"
            )}
            actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
            if event.get("previous_hash", "") != previous_hash:
                errors.append(f"event {index} has an invalid previous hash")
            if expected != actual:
                errors.append(f"event {index} has an invalid event hash")
            previous_hash = expected
        return not errors, errors

    def verify_completeness(self) -> Tuple[bool, List[str]]:
        """Verify required fields for all events and the hash chain."""
        errors: List[str] = []
        for index, event in enumerate(self._events()):
            for key in ("event_id", "event_type", "actor", "timestamp", "event_hash"):
                if not event.get(key):
                    errors.append(f"event {index} is missing {key}")
            if event.get("event_type") == "human_staging_decision" and not event.get("details", {}).get("human_attributed"):
                errors.append(f"event {index} is missing human attribution")
        valid, integrity_errors = self.verify_integrity()
        if not valid:
            errors.extend(integrity_errors)
        return not errors, errors

    def read(self) -> List[Dict[str, Any]]:
        """Return a copy of all persisted events."""
        return list(self._events())


class SurgeonsTableWorkflow:
    """Validate Surgeon’s Table records and prevent unattributed publication."""

    def validate_record(self, record: Any) -> List[str]:
        """Return workflow violations for a staging record or table row."""
        def value(name: str, default: Any = "") -> Any:
            if isinstance(record, Mapping):
                return record.get(name, default)
            return getattr(record, name, default)

        issues: List[str] = []
        aliases = {
            "subject": ("Subject",),
            "predicate": ("Predicate",),
            "object": ("Object",),
            "evidence": ("Evidence", "Evidence Quote", "evidence_quote"),
        }
        for name, alternative_keys in aliases.items():
            candidate = value(name)
            if not candidate and isinstance(record, Mapping):
                for alternative in alternative_keys:
                    candidate = record.get(alternative, "")
                    if candidate:
                        break
            if not str(candidate or "").strip():
                issues.append(f"Missing {name}")
        raw_status = value("validation_status", value("SHACL Status", "valid"))
        status = str(getattr(raw_status, "value", raw_status)).lower()
        if status not in {"valid", "quarantined", "invalid", "pending_review"}:
            issues.append(f"Unknown SHACL status: {status}")
        raw_approval = value("approval_status", value("Approval Status", "pending")) or "pending"
        approval = str(getattr(raw_approval, "value", raw_approval)).lower()
        reviewer = str(value("reviewed_by", value("reviewer", "")) or "").strip()
        if approval in APPROVED_DECISIONS and reviewer.casefold() in AUTOMATED_ACTORS:
            issues.append("Live graph publication lacks human attribution")
        return issues

    def can_publish(self, record: Any, reviewer: str, *, edited: bool = False, reason: str = "") -> bool:
        """Return whether a proposed Surgeon’s Table decision is publishable."""
        if not reviewer.strip() or reviewer.casefold() in AUTOMATED_ACTORS:
            return False
        issues = self.validate_record(record)
        if issues:
            return False
        if isinstance(record, Mapping):
            raw_status = record.get("validation_status", record.get("SHACL Status", "valid"))
        else:
            raw_status = getattr(record, "validation_status", "valid")
        status = str(getattr(raw_status, "value", raw_status)).lower()
        if status in {"invalid", "pending_review"} and not edited:
            return False
        if status == "quarantined" and not (edited or reason.strip()):
            return False
        return True

    def validate_records(self, records: Iterable[Any]) -> Dict[str, Any]:
        """Validate a batch and return a stable report for audit evidence."""
        materialized = list(records)
        all_issues: Dict[str, List[str]] = {}
        for index, record in enumerate(materialized):
            issues = self.validate_record(record)
            if issues:
                all_issues[str(index)] = issues
        return {"valid": not all_issues, "invalid_records": all_issues, "total": len(materialized)}


class RetrievalTransparency:
    """Expose graph/vector weights and contributions used by hybrid retrieval."""

    @staticmethod
    def _score(result: Any) -> float:
        return float(result.get("score", 0.0) if isinstance(result, Mapping) else getattr(result, "score", 0.0))

    @classmethod
    def report(cls, alpha: float, graph_results: Sequence[Any], vector_results: Sequence[Any]) -> Dict[str, Any]:
        """Build an explainable retrieval contribution report."""
        if not 0.0 <= float(alpha) <= 1.0:
            raise ComplianceError("Retrieval alpha must be between 0 and 1")
        graph_weight = float(alpha)
        vector_weight = 1.0 - graph_weight
        graph = [{"score": cls._score(item), "weighted_score": cls._score(item) * graph_weight} for item in graph_results]
        vector = [{"score": cls._score(item), "weighted_score": cls._score(item) * vector_weight} for item in vector_results]
        return {
            "alpha": graph_weight,
            "graph_weight": graph_weight,
            "vector_weight": vector_weight,
            "graph_result_count": len(graph),
            "vector_result_count": len(vector),
            "graph_contribution": sum(item["weighted_score"] for item in graph),
            "vector_contribution": sum(item["weighted_score"] for item in vector),
            "graph_results": graph,
            "vector_results": vector,
        }

    build_report = report


def verify_air_gapped_operation(**kwargs: Any) -> AirGapReport:
    """Convenience function used by startup checks and tests."""
    return AirGapVerifier(**kwargs).verify()


__all__ = [
    "AirGapReport",
    "AirGapVerifier",
    "AuditEvent",
    "ComplianceAuditTrail",
    "ComplianceError",
    "DeterministicGuardrails",
    "GuardrailResult",
    "GuardrailTestReport",
    "RetrievalTransparency",
    "SurgeonsTableWorkflow",
    "verify_air_gapped_operation",
]
