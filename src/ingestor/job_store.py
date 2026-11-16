"""Durable, atomically updated local manifests for ingestion jobs."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import threading
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from .job_models import (
    IngestionJobStatus,
    JobConfiguration,
    JobDiagnostic,
    JobLifecycleStatus,
    JobProgress,
    JobResult,
    JobStage,
    SourceMetadata,
)


class JobStoreError(RuntimeError):
    """Base error for durable job-store failures."""


class UnknownJobError(JobStoreError, KeyError):
    """The requested job manifest does not exist."""


class InvalidJobTransition(JobStoreError):
    """A lifecycle transition or terminal mutation was not allowed."""


class JobClaimedError(JobStoreError):
    """Another worker already claimed the queued job."""


class IngestionJobStore:
    """Persist one status manifest per job with atomic replacement."""

    def __init__(self, root: Path = Path("data/tmp/ingestion_jobs")) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create_job(
        self,
        source: SourceMetadata,
        configuration: Optional[JobConfiguration] = None,
        source_path: Optional[Path] = None,
        job_id: Optional[str] = None,
    ) -> IngestionJobStatus:
        """Create an atomically persisted queued manifest."""
        job_id = job_id or f"ing-{uuid4().hex}"
        now = IngestionJobStatus.now()
        status = IngestionJobStatus(
            job_id=job_id,
            status=JobLifecycleStatus.QUEUED,
            stage=JobStage.QUEUED,
            source=source,
            configuration=configuration or JobConfiguration(),
            created_at=now,
            updated_at=now,
        )
        manifest = status.model_dump(mode="json")
        manifest["_source_path"] = str(source_path) if source_path else None
        manifest["_checkpoint_path"] = str(self.job_dir(job_id) / "checkpoint.json")
        manifest["_generation"] = 0
        with self._lock:
            if self.manifest_path(job_id).exists():
                raise JobStoreError(f"Job already exists: {job_id}")
            self.job_dir(job_id).mkdir(parents=True, exist_ok=True)
            self._write_manifest(job_id, manifest)
        return status

    def delete_job(self, job_id: str) -> None:
        """Delete a pre-queue manifest when the runner rejects submission."""
        with self._lock:
            path = self.manifest_path(job_id)
            if path.exists():
                data = self._read_manifest(job_id)
                if data.get("status") != JobLifecycleStatus.QUEUED.value:
                    raise InvalidJobTransition("only queued jobs can be deleted")
                for child in self.job_dir(job_id).iterdir():
                    child.unlink(missing_ok=True)
                self.job_dir(job_id).rmdir()

        """Return the private directory for one job."""
        return self.root / job_id

    def manifest_path(self, job_id: str) -> Path:
        """Return the status manifest path for one job."""
        return self.job_dir(job_id) / "status.json"

    def event_log_path(self, job_id: str) -> Path:
        """Return the append-only private event log path."""
        return self.job_dir(job_id) / "events.jsonl"

    def get(self, job_id: str) -> IngestionJobStatus:
        """Read and validate a complete public status snapshot."""
        with self._lock:
            data = self._read_manifest(job_id)
        return IngestionJobStatus.model_validate(self._public_data(data))

    def get_internal(self, job_id: str) -> Dict[str, Any]:
        """Read private manifest data for trusted worker components."""
        with self._lock:
            return self._read_manifest(job_id)

    def claim(self, job_id: str) -> IngestionJobStatus:
        """Compare-and-set a queued job to running."""
        with self._lock:
            data = self._read_manifest(job_id)
            current = JobLifecycleStatus(data["status"])
            if current != JobLifecycleStatus.QUEUED:
                raise JobClaimedError(f"Job {job_id} is {current.value}")
            now = IngestionJobStatus.now()
            data.update({
                "status": JobLifecycleStatus.RUNNING.value,
                "stage": JobStage.PARSING.value,
                "started_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "_generation": int(data.get("_generation", 0)) + 1,
            })
            self._write_manifest(job_id, data)
            self._append_event(job_id, {"event": "claimed", "at": now.isoformat()})
            return IngestionJobStatus.model_validate(self._public_data(data))

    def update(
        self,
        job_id: str,
        *,
        status: Optional[JobLifecycleStatus] = None,
        stage: Optional[JobStage] = None,
        progress: Optional[JobProgress] = None,
        result: Optional[JobResult] = None,
        diagnostic: Optional[JobDiagnostic] = None,
        completed_chunk_ids: Optional[Iterable[str]] = None,
        expected_generation: Optional[int] = None,
    ) -> IngestionJobStatus:
        """Apply a validated monotonic update and atomically replace the manifest."""
        with self._lock:
            data = self._read_manifest(job_id)
            current_status = JobLifecycleStatus(data["status"])
            generation = int(data.get("_generation", 0))
            if expected_generation is not None and expected_generation != generation:
                raise InvalidJobTransition("stale job generation")
            if current_status in JobLifecycleStatus.terminal():
                if status and status != current_status:
                    raise InvalidJobTransition("terminal job status is immutable")
                if progress or stage or result or completed_chunk_ids:
                    raise InvalidJobTransition("terminal job fields are immutable")
            if status and not self._allowed(current_status, status):
                raise InvalidJobTransition(
                    f"invalid transition {current_status.value} -> {status.value}"
                )
            if status:
                data["status"] = status.value
            if stage:
                data["stage"] = stage.value
            if progress:
                previous = JobProgress.model_validate(data.get("progress", {}))
                self._ensure_monotonic(previous, progress)
                data["progress"] = progress.model_dump(mode="json")
            if result is not None:
                data["result"] = result.model_dump(mode="json")
            if diagnostic is not None:
                data.setdefault("diagnostics", []).append(diagnostic.model_dump(mode="json"))
            if completed_chunk_ids is not None:
                existing = list(data.get("completed_chunk_ids", []))
                for chunk_id in completed_chunk_ids:
                    if chunk_id not in existing:
                        existing.append(chunk_id)
                data["completed_chunk_ids"] = existing
            now = IngestionJobStatus.now()
            data["updated_at"] = now.isoformat()
            if status in JobLifecycleStatus.terminal():
                data["completed_at"] = now.isoformat()
            data["_generation"] = generation + 1
            self._write_manifest(job_id, data)
            self._append_event(job_id, {"event": "updated", "at": now.isoformat()})
            return IngestionJobStatus.model_validate(self._public_data(data))

    def append_diagnostic(self, job_id: str, diagnostic: JobDiagnostic) -> IngestionJobStatus:
        """Persist a warning or error without exposing private event data."""
        return self.update(job_id, diagnostic=diagnostic)

    def recover_stale(self, max_age_seconds: float = 300.0) -> list[str]:
        """Mark stale running workers failed with a safe recovery diagnostic."""
        recovered = []
        cutoff = IngestionJobStatus.now() - timedelta(seconds=max_age_seconds)
        with self._lock:
            for path in self.root.glob("*/status.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("status") != JobLifecycleStatus.RUNNING.value:
                        continue
                    updated = IngestionJobStatus.model_validate(self._public_data(data)).updated_at
                    if updated >= cutoff:
                        continue
                    job_id = str(data["job_id"])
                    diagnostic = JobDiagnostic(
                        code="JOB_WORKER_INTERRUPTED",
                        stage=JobStage.FAILED,
                        message="The ingestion worker stopped before the job completed.",
                        retryable=True,
                    )
                    self.update(job_id, status=JobLifecycleStatus.FAILED, stage=JobStage.FAILED,
                                diagnostic=diagnostic)
                    recovered.append(job_id)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        return recovered

    @staticmethod
    def _allowed(current: JobLifecycleStatus, target: JobLifecycleStatus) -> bool:
        """Validate lifecycle transitions."""
        return target == current or (
            current == JobLifecycleStatus.QUEUED and target == JobLifecycleStatus.RUNNING
        ) or (
            current == JobLifecycleStatus.RUNNING and target in JobLifecycleStatus.terminal()
        )

    @staticmethod
    def _ensure_monotonic(previous: JobProgress, current: JobProgress) -> None:
        """Reject progress counters or fractions that move backwards."""
        for field in JobProgress.model_fields:
            if getattr(current, field) < getattr(previous, field):
                raise InvalidJobTransition(f"progress field decreased: {field}")

    def _read_manifest(self, job_id: str) -> Dict[str, Any]:
        path = self.manifest_path(job_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise UnknownJobError(job_id) from error
        except (OSError, ValueError, TypeError) as error:
            raise JobStoreError(f"Unable to read job manifest {job_id}") from error

    def _write_manifest(self, job_id: str, data: Dict[str, Any]) -> None:
        path = self.manifest_path(job_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _append_event(self, job_id: str, event: Dict[str, Any]) -> None:
        try:
            with self.event_log_path(job_id).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        except OSError:
            return

    @staticmethod
    def _public_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove trusted-only path and generation fields before validation/return."""
        return {key: value for key, value in deepcopy(data).items() if not key.startswith("_")}
