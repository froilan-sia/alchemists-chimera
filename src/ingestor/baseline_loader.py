"""Idempotent bootstrap ingestion for the checked-in baseline corpus."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from rdflib import Graph, Literal, Namespace, RDF

from ..config import settings
from ..vector_store import VectorStore

logger = logging.getLogger(__name__)

BASELINE_FILENAMES = (
    "basel_iii_framework.pdf",
    "hkma_capital_requirements.pdf",
    "risk_weighted_assets.pdf",
    "test_hkma_basel.pdf",
)
CHIMERA = Namespace("http://example.org/chimera#")
BASELINE_DOCUMENT = CHIMERA.BaselineDocument


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


class BaselineCorpusLoader:
    """Load baseline PDFs only when their content is absent from both stores."""

    def __init__(
        self,
        baseline_dir: Path = Path("data/input"),
        vector_store: Optional[Any] = None,
        graph_path: Path = Path("data/knowledge_graph.ttl"),
        pipeline_factory: Optional[Callable[..., Any]] = None,
        file_names: Iterable[str] = BASELINE_FILENAMES,
    ) -> None:
        self.baseline_dir = Path(baseline_dir)
        self.vector_store = vector_store
        self.graph_path = Path(graph_path)
        self.pipeline_factory = pipeline_factory
        self.file_names = tuple(file_names)

    def load(self) -> Dict[str, str]:
        """Ingest missing baseline files and return per-file actions."""
        actions: Dict[str, str] = {}
        for file_name in self.file_names:
            path = self.baseline_dir / file_name
            if not path.is_file():
                logger.warning("Baseline PDF is missing: %s", path)
                actions[file_name] = "missing"
                continue
            source_hash = sha256_file(path)
            vector_indexed = self._vector_indexed(source_hash, path.name)
            graph_indexed = self._graph_indexed(source_hash, path.name)
            if vector_indexed and graph_indexed:
                actions[file_name] = "skipped"
                continue

            pipeline = self._make_pipeline()
            # The pipeline writes stable chunk IDs and source_sha256 metadata.
            pipeline.process_pdf(path)
            self._write_graph_marker(path.name, source_hash)
            actions[file_name] = "ingested"
        return actions

    def _make_pipeline(self) -> Any:
        """Create a pipeline lazily so an already-indexed corpus is cheap."""
        if self.pipeline_factory is not None:
            try:
                return self.pipeline_factory(
                    vector_store_path=str(getattr(self.vector_store, "persist_directory", settings.vector_store_path)),
                    baseline=True,
                    require_human_approval=False,
                )
            except TypeError:
                return self.pipeline_factory()
        from .pipeline import IngestionPipeline

        return IngestionPipeline(
            {
                "vector_store_path": str(
                    getattr(self.vector_store, "persist_directory", settings.vector_store_path)
                ),
                "baseline": True,
                "require_human_approval": False,
            }
        )

    def _get_vector_store(self) -> Any:
        if self.vector_store is None:
            self.vector_store = VectorStore(settings.vector_store_path)
            self.vector_store.initialize()
        return self.vector_store

    def _vector_indexed(self, source_hash: str, file_name: str) -> bool:
        """Check Chroma metadata for a source marker, migrating old names."""
        store = self._get_vector_store()
        checker = getattr(store, "has_source_hash", None)
        if callable(checker) and checker(source_hash):
            return True
        collection = getattr(store, "collection", None)
        getter = getattr(collection, "get", None)
        if not callable(getter):
            return False
        try:
            result = getter(where={"source_sha256": source_hash}, include=["metadatas"])
        except (TypeError, ValueError):
            result = None
        if result and result.get("ids"):
            return True
        # Older entries had the display filename but not a content digest. Add
        # the digest once so future startup checks remain content-addressed.
        try:
            legacy = getter(
                where={"document_name": file_name},
                include=["metadatas", "ids"],
            )
            ids = legacy.get("ids", []) if legacy else []
            metadatas = legacy.get("metadatas", []) if legacy else []
            if ids and hasattr(collection, "update"):
                updated = []
                for metadata in metadatas:
                    item = dict(metadata or {})
                    item["source_sha256"] = source_hash
                    updated.append(item)
                collection.update(ids=ids, metadatas=updated)
                return True
        except (TypeError, ValueError):
            return False
        return False

    def _graph_indexed(self, source_hash: str, file_name: str) -> bool:
        """Check the RDF manifest for a digest and migrate old file markers."""
        graph = Graph()
        if self.graph_path.exists():
            try:
                graph.parse(self.graph_path, format="turtle")
            except Exception as error:
                logger.warning("Unable to read baseline graph manifest: %s", error)
                return False
        if any(str(value) == source_hash for value in graph.objects(None, CHIMERA.sourceSha256)):
            return True
        legacy_subjects = list(graph.subjects(CHIMERA.sourceDocument, Literal(file_name)))
        if legacy_subjects:
            for subject in legacy_subjects:
                graph.add((subject, CHIMERA.sourceSha256, Literal(source_hash)))
            self.graph_path.parent.mkdir(parents=True, exist_ok=True)
            self.graph_path.write_text(graph.serialize(format="turtle"), encoding="utf-8")
            return True
        return False

    def _write_graph_marker(self, file_name: str, source_hash: str) -> None:
        """Persist one idempotent source marker in the local RDF store."""
        graph = Graph()
        if self.graph_path.exists():
            try:
                graph.parse(self.graph_path, format="turtle")
            except Exception as error:
                logger.warning("Rebuilding unreadable baseline graph: %s", error)
        graph.bind("chimera", CHIMERA)
        marker = CHIMERA[f"baseline-document-{source_hash}"]
        graph.add((marker, RDF.type, BASELINE_DOCUMENT))
        graph.add((marker, CHIMERA.sourceSha256, Literal(source_hash)))
        graph.add((marker, CHIMERA.sourceDocument, Literal(file_name)))
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.graph_path.with_suffix(".tmp.ttl")
        temporary.write_text(graph.serialize(format="turtle"), encoding="utf-8")
        temporary.replace(self.graph_path)


def bootstrap_baseline_corpus(**kwargs: Any) -> Dict[str, str]:
    """Convenience entry point for API startup and command-line bootstrap."""
    return BaselineCorpusLoader(**kwargs).load()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(bootstrap_baseline_corpus())
