"""Bounded asynchronous execution for durable ingestion jobs."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .job_models import (
    IngestionJobStatus,
    JobConfiguration,
    JobDiagnostic,
    JobLifecycleStatus,
    JobProgress,
    JobResult,
    JobStage,
)
from .job_store import (
    IngestionJobStore,
    InvalidJobTransition,
    JobClaimedError,
    UnknownJobError,
)
from .pipeline import IngestionPipeline, PipelineMetrics, PipelineStatus

logger = logging.getLogger(__name__)


class RunnerUnavailableError(RuntimeError):
    """The runner cannot accept another queued job."""


@dataclass
class RunnerLimits:
    """Concurrency limits for local asynchronous ingestion."""

    max_queue_size: int = 32
    max_active_jobs: int = 2
    max_active_chunks: int = 1
    max_entity_tasks: int = 2
    max_llm_calls: int = 1
    max_persistence_operations: int = 1


class AsyncIngestionJobRunner:
    """Own queue workers and run blocking pipeline work outside the event loop."""

    def __init__(
        self,
        store: IngestionJobStore,
        pipeline_factory: Optional[Callable[..., IngestionPipeline]] = None,
        limits: Optional[RunnerLimits] = None,
    ) -> None:
        self.store = store
        self.pipeline_factory = pipeline_factory or IngestionPipeline
        self.limits = limits or RunnerLimits()
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.limits.max_queue_size)
        self._active = asyncio.Semaphore(self.limits.max_active_jobs)
        self._workers: list[asyncio.Task[None]] = []
        self._owned_jobs: set[str] = set()
        self._running = False

    async def start(self) -> None:
        """Start explicit queue workers once."""
        if self._running:
            return
        self._running = True
        self.store.recover_stale()
        self._workers = [
            asyncio.create_task(self._worker(), name=f"ingestion-worker-{index}")
            for index in range(self.limits.max_active_jobs)
        ]

    async def stop(self, timeout: float = 30.0) -> None:
        """Drain owned jobs and stop worker tasks without abandoning manifests."""
        if not self._running:
            return
        self._running = False
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            for job_id in list(self._owned_jobs):
                with suppress(Exception):
                    self.store.update(
                        job_id,
                        status=JobLifecycleStatus.CANCELED,
                        stage=JobStage.CANCELED,
                        diagnostic=JobDiagnostic(
                            code="JOB_SHUTDOWN_TIMEOUT",
                            stage=JobStage.CANCELED,
                            message="The application stopped before ingestion completed.",
                            retryable=True,
                        ),
                    )
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(self, job_id: str) -> None:
        """Queue a created job or report that the queue is full/unavailable."""
        if not self._running:
            raise RunnerUnavailableError("Ingestion runner is not started")
        try:
            self.queue.put_nowait(job_id)
        except asyncio.QueueFull as error:
            raise RunnerUnavailableError("Ingestion queue is full") from error

    async def _worker(self) -> None:
        while self._running or not self.queue.empty():
            try:
                job_id = await asyncio.wait_for(self.queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            try:
                async with self._active:
                    await self._run_job(job_id)
            finally:
                self.queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        try:
            claimed = self.store.claim(job_id)
        except (UnknownJobError, JobClaimedError):
            return
        self._owned_jobs.add(job_id)
        try:
            metrics = await asyncio.to_thread(self._execute_sync, claimed)
            current = self.store.get(job_id)
            if current.status in JobLifecycleStatus.terminal():
                return
            result = self._result(metrics)
            terminal = (
                JobLifecycleStatus.PARTIAL
                if metrics.failed_chunks or getattr(metrics, "status", None) == PipelineStatus.PARTIAL
                else JobLifecycleStatus.COMPLETED
            )
            self.store.update(
                job_id,
                status=terminal,
                stage=JobStage.COMPLETED if terminal == JobLifecycleStatus.COMPLETED else JobStage.FINALIZING,
                result=result,
                progress=self._final_progress(current.progress, terminal),
            )
            if terminal == JobLifecycleStatus.PARTIAL and not current.diagnostics:
                self.store.append_diagnostic(
                    job_id,
                    JobDiagnostic(
                        code="CHUNK_PROCESSING_FAILED",
                        stage=JobStage.EXTRACTING_TRIPLES,
                        message="One or more chunks could not be completed.",
                        retryable=True,
                    ),
                )
        except asyncio.CancelledError:
            with suppress(Exception):
                self.store.update(
                    job_id,
                    status=JobLifecycleStatus.CANCELED,
                    stage=JobStage.CANCELED,
                    diagnostic=JobDiagnostic(
                        code="JOB_CANCELED",
                        stage=JobStage.CANCELED,
                        message="The ingestion job was canceled before completion.",
                        retryable=True,
                    ),
                )
            raise
        except Exception as error:
            logger.exception("Ingestion job %s failed", job_id)
            with suppress(Exception):
                self.store.update(
                    job_id,
                    status=JobLifecycleStatus.FAILED,
                    stage=JobStage.FAILED,
                    diagnostic=JobDiagnostic(
                        code="PDF_PARSE_FAILED" if "parse" in str(error).lower() else "JOB_FAILED",
                        stage=JobStage.FAILED,
                        message="The ingestion job could not be completed.",
                        retryable=True,
                    ),
                )
        finally:
            self._owned_jobs.discard(job_id)

    def _execute_sync(self, status: IngestionJobStatus) -> PipelineMetrics:
        """Execute blocking parser/extractor/store calls in a worker thread."""
        manifest = self.store.get_internal(status.job_id)
        source_path = manifest.get("_source_path")
        if not source_path:
            raise RuntimeError("job source is unavailable")
        config = status.configuration
        try:
            pipeline = self.pipeline_factory(
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                checkpoint_path=manifest.get("_checkpoint_path"),
            )
        except TypeError:
            pipeline = self.pipeline_factory({
                "chunk_size": config.chunk_size,
                "chunk_overlap": config.chunk_overlap,
                "checkpoint_path": manifest.get("_checkpoint_path"),
            })

        def emit(event: Dict[str, Any]) -> None:
            self._handle_event(status.job_id, event)

        return pipeline.process_pdf_job(
            Path(source_path),
            Path(manifest["_checkpoint_path"]),
            status.source.content_sha256,
            progress_sink=emit,
        )

    def _handle_event(self, job_id: str, event: Dict[str, Any]) -> None:
        """Translate internal progress events to a monotonic public snapshot."""
        with suppress((UnknownJobError, InvalidJobTransition, ValueError, TypeError)):
            current = self.store.get(job_id)
            if current.status in JobLifecycleStatus.terminal():
                return
            stage_name = str(event.get("stage", "parsing"))
            stage = JobStage(stage_name) if stage_name in {item.value for item in JobStage} else current.stage
            updates = current.progress.model_dump()
            for field in updates:
                value = event.get(field)
                if isinstance(value, (int, float)):
                    updates[field] = max(updates[field], value)
            if updates["pages_total"]:
                updates["fraction"] = max(
                    updates["fraction"],
                    min(0.99, updates["pages_processed"] / updates["pages_total"] * 0.4),
                )
            if updates["chunks_discovered"]:
                updates["fraction"] = max(
                    updates["fraction"],
                    min(0.99, updates["chunks_processed"] / max(updates["chunks_discovered"], 1) * 0.9),
                )
            self.store.update(job_id, stage=stage, progress=JobProgress(**updates))
            diagnostic = event.get("diagnostic")
            if diagnostic:
                self.store.append_diagnostic(job_id, JobDiagnostic(**diagnostic))

    @staticmethod
    def _result(metrics: PipelineMetrics) -> JobResult:
        """Convert pipeline metrics into the public terminal result."""
        return JobResult(
            total_chunks=metrics.total_chunks,
            processed_chunks=metrics.processed_chunks,
            failed_chunks=metrics.failed_chunks,
            total_triples=metrics.total_triples,
            valid_triples=metrics.valid_triples,
            quarantined_triples=metrics.quarantined_triples,
            vector_insertions=metrics.vector_insertions,
            duration_seconds=metrics.duration_seconds,
        )

    @staticmethod
    def _final_progress(progress: JobProgress, terminal: JobLifecycleStatus) -> JobProgress:
        """Finalize progress without decreasing any observed counter."""
        values = progress.model_dump()
        if terminal == JobLifecycleStatus.COMPLETED:
            values["fraction"] = 1.0
        return JobProgress(**values)
