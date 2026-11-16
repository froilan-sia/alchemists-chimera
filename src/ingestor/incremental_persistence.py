"""Idempotent per-chunk persistence for asynchronous ingestion jobs."""

import hashlib
import json
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from .pdf_parser import PDFChunk


class IncrementalPersistenceError(RuntimeError):
    """A required vector, staging, or checkpoint write failed."""


class IncrementalPersistenceCoordinator:
    """Serialize vector/staging writes and advance checkpoints after success."""

    def __init__(
        self,
        vector_store: Any,
        staging_manager: Any,
        source_hash: str,
        configuration: Optional[Dict[str, Any]] = None,
        checkpoint: Optional[Dict[str, Any]] = None,
        checkpoint_writer: Optional[Callable[[Dict[str, Any]], None]] = None,
        progress_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.vector_store = vector_store
        self.staging_manager = staging_manager
        self.source_hash = source_hash
        self.configuration = configuration or {}
        self.checkpoint = checkpoint if checkpoint is not None else {}
        self.checkpoint_writer = checkpoint_writer
        self.progress_sink = progress_sink
        self._lock = RLock()
        self.completed_chunks: Set[str] = set(self.checkpoint.setdefault("processed_chunks", []))
        self.persistence_keys: Set[str] = set(self.checkpoint.setdefault("persistence_keys", []))
        self.staging_record_ids: List[str] = list(self.checkpoint.setdefault("staging_record_ids", []))

    def persist_chunk(self, chunk: PDFChunk, staging_records: Iterable[Any]) -> None:
        """Persist one chunk and mark it complete only after all required writes."""
        with self._lock:
            if chunk.id in self.completed_chunks:
                return
            try:
                self._persist_vector(chunk)
                self._emit("vector_persisted", chunk_id=chunk.id)
                for index, record in enumerate(staging_records):
                    key = self.staging_key(chunk, record, index)
                    if key in self.persistence_keys:
                        continue
                    # The key is durable before the potentially non-idempotent
                    # staging call. Existing records are therefore skipped on replay.
                    self.persistence_keys.add(key)
                    self._write_checkpoint()
                    record_id = self.staging_manager.add_record(record)
                    if record_id is not None:
                        self.staging_record_ids.append(str(record_id))
                    self._emit("staging_persisted", chunk_id=chunk.id)
                self.completed_chunks.add(chunk.id)
                self.checkpoint["processed_chunks"] = sorted(self.completed_chunks)
                self._write_checkpoint()
                self._emit("chunk_completed", chunk_id=chunk.id)
            except Exception as error:
                self._emit("persistence_failed", chunk_id=chunk.id)
                raise IncrementalPersistenceError(
                    f"Persistence failed for chunk {chunk.id}."
                ) from error

    def _persist_vector(self, chunk: PDFChunk) -> None:
        """Use stable IDs and support older injected vector-store signatures."""
        metadata = dict(chunk.metadata)
        metadata.update({
            "chunk_id": chunk.id,
            "page_number": chunk.page_number,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "chunk_index": chunk.chunk_index,
            "source_sha256": self.source_hash,
        })
        try:
            upsert = getattr(self.vector_store, "upsert_documents", None)
            if callable(upsert):
                upsert(documents=[chunk.text], metadata=[metadata], ids=[chunk.id])
                return
            result = self.vector_store.add_documents(
                documents=[chunk.text], metadata=[metadata], ids=[chunk.id]
            )
        except TypeError:
            result = self.vector_store.add_documents(
                documents=[chunk.text], metadata=[metadata]
            )
        if result is None:
            raise IncrementalPersistenceError("Vector store did not acknowledge the write.")

    def _write_checkpoint(self) -> None:
        """Persist the current replay ledger before advancing work."""
        self.checkpoint["persistence_keys"] = sorted(self.persistence_keys)
        self.checkpoint["staging_record_ids"] = list(self.staging_record_ids)
        if self.checkpoint_writer is not None:
            self.checkpoint_writer(self.checkpoint)

    def _emit(self, event: str, **values: Any) -> None:
        if self.progress_sink is not None:
            self.progress_sink({"event": event, **values})

    def staging_key(self, chunk: PDFChunk, record: Any, index: int = 0) -> str:
        """Return a deterministic source/config/chunk/triple fingerprint."""
        triple = getattr(record, "triple", record)
        payload = {
            "source": self.source_hash,
            "chunk": chunk.id,
            "index": index,
            "subject": str(getattr(triple, "subject", "")),
            "predicate": str(getattr(triple, "predicate", "")),
            "object": str(getattr(triple, "object", "")),
            "evidence": str(getattr(triple, "evidence", "")),
            "configuration": self.configuration,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
