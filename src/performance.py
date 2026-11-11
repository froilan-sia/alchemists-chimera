"""Performance controls, resource limits, and lightweight monitoring utilities.

The ingestion pipeline uses these helpers to keep CPU-bound preprocessing bounded,
record stage timings, and prevent an unexpectedly large document from exhausting
the Hugging Face Spaces free tier. Ollama inference remains sequential in the
pipeline; this module does not parallelize LLM calls.
"""

from __future__ import annotations

import logging
import resource
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PerformanceConfig(BaseModel):
    """Configurable limits for PDF ingestion and persistence operations."""

    batch_size: int = Field(default=8, ge=1, le=256)
    max_workers: int = Field(default=2, ge=1, le=16)
    chunk_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)
    pdf_timeout_seconds: float = Field(default=300.0, gt=0, le=7200)
    memory_limit_mb: int = Field(default=2048, ge=128, le=65536)
    max_chunks: int = Field(default=10000, ge=1, le=1_000_000)
    database_pool_size: int = Field(default=4, ge=1, le=64)
    enable_parallel_preprocessing: bool = True
    monitor_interval_seconds: float = Field(default=1.0, gt=0, le=60)


class ResourceLimitError(RuntimeError):
    """Raised when an ingestion operation exceeds a configured resource limit."""


class FileContentCache:
    """Thread-safe mtime-aware cache for ontology and SHACL text files."""

    _lock = threading.RLock()
    _entries: Dict[str, tuple[int, int, str]] = {}

    @classmethod
    def get_text(cls, path: Path, encoding: str = "utf-8") -> str:
        """Return cached file content and invalidate it when the file changes."""
        resolved = Path(path).expanduser().resolve()
        stat = resolved.stat()
        key = str(resolved)
        signature = (stat.st_mtime_ns, stat.st_size)
        with cls._lock:
            cached = cls._entries.get(key)
            if cached and cached[:2] == signature:
                return cached[2]
            content = resolved.read_text(encoding=encoding)
            cls._entries[key] = (signature[0], signature[1], content)
            return content

    @classmethod
    def clear(cls) -> None:
        """Clear all cached file contents, primarily for tests and reloads."""
        with cls._lock:
            cls._entries.clear()


class DatabaseConnectionPool:
    """Bound concurrent database operations with a reusable semaphore.

    ChromaDB owns its underlying SQLite connections, so callers cannot safely
    replace them. This pool limits concurrent operations against the persistent
    client and makes that constraint explicit for both Chroma and test stores.
    """

    def __init__(self, max_connections: int = 4):
        if max_connections < 1:
            raise ValueError("max_connections must be at least 1")
        self.max_connections = max_connections
        self._semaphore = threading.BoundedSemaphore(max_connections)
        self._lock = threading.Lock()
        self._active = 0

    @contextmanager
    def connection(self) -> Iterator[None]:
        """Acquire one operation slot and release it even if the operation fails."""
        self._semaphore.acquire()
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
            self._semaphore.release()

    def status(self) -> Dict[str, int]:
        """Return pool capacity and current usage."""
        with self._lock:
            active = self._active
        return {
            "max_connections": self.max_connections,
            "active_connections": active,
            "available_connections": self.max_connections - active,
        }


@dataclass
class PerformanceMonitor:
    """Collect thread-safe stage timings and counters for a pipeline run."""

    counters: Dict[str, int] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a named counter."""
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + amount

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Record elapsed wall-clock time for a named stage."""
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            with self._lock:
                self.timings[name] = self.timings.get(name, 0.0) + elapsed

    def snapshot(self) -> Dict[str, Dict[str, float | int]]:
        """Return a serializable copy suitable for logs and Streamlit."""
        with self._lock:
            return {
                "counters": dict(self.counters),
                "timings": dict(self.timings),
            }


class ResourceLimiter:
    """Enforce elapsed-time, chunk-count, and best-effort memory limits."""

    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.started = time.perf_counter()

    @property
    def memory_usage_mb(self) -> float:
        """Return the process's maximum resident set size in megabytes."""
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kilobytes.
        if usage > 1024 * 1024 * 10:
            return usage / (1024 * 1024)
        return usage / 1024

    def check(self, chunks_seen: Optional[int] = None) -> None:
        """Raise ResourceLimitError when a configured limit has been exceeded."""
        elapsed = time.perf_counter() - self.started
        if elapsed > self.config.pdf_timeout_seconds:
            raise ResourceLimitError(
                f"PDF processing exceeded {self.config.pdf_timeout_seconds:.1f}s timeout"
            )
        if chunks_seen is not None and chunks_seen > self.config.max_chunks:
            raise ResourceLimitError(
                f"PDF contains more than the configured {self.config.max_chunks} chunks"
            )
        memory_mb = self.memory_usage_mb
        if memory_mb > self.config.memory_limit_mb:
            raise ResourceLimitError(
                f"PDF processing exceeded {self.config.memory_limit_mb} MB memory limit"
            )
