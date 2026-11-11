"""Helpers for the Hybrid Chimera Chat audit interface.

The Streamlit layer is intentionally thin. These helpers keep query result
classification, alpha calculations, provenance links, and citation formatting
independent from Streamlit so they can be tested without a running app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote

from src.models import HybridResponse, QueryRequest, RetrievalResult, RetrievalSource


@dataclass
class ChatQueryResult:
    """Response and audit data produced by one hybrid query."""

    request: QueryRequest
    response: HybridResponse
    graph_results: List[RetrievalResult]
    vector_results: List[RetrievalResult]
    alpha: float


@dataclass
class QueryHistoryEntry:
    """Serializable query history item stored in Streamlit session state."""

    query: str
    query_type: str
    alpha: float
    confidence: float
    processing_time: float
    timestamp: str
    answer: str
    favorite: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary suitable for ``st.session_state``."""
        return {
            "query": self.query,
            "query_type": self.query_type,
            "alpha": self.alpha,
            "confidence": self.confidence,
            "processing_time": self.processing_time,
            "timestamp": self.timestamp,
            "answer": self.answer,
            "favorite": self.favorite,
        }


def split_retrieval_results(
    results: Iterable[RetrievalResult],
) -> tuple[List[RetrievalResult], List[RetrievalResult]]:
    """Split fused results into graph and vector audit streams.

    ``FusionEngine`` stores the original branch in ``metadata``. The fallback
    checks preserve useful behavior for older results and mock responses that
    only expose ``source`` or ``entity_links``.
    """
    graph_results: List[RetrievalResult] = []
    vector_results: List[RetrievalResult] = []

    for result in results:
        original_source = str(result.metadata.get("original_source", "")).lower()
        if original_source == RetrievalSource.GRAPH.value:
            graph_results.append(result)
        elif original_source == RetrievalSource.VECTOR.value:
            vector_results.append(result)
        elif result.source == RetrievalSource.GRAPH or result.entity_links:
            graph_results.append(result)
        else:
            vector_results.append(result)

    return graph_results, vector_results


def provenance_link(result: RetrievalResult) -> Optional[str]:
    """Build a safe, human-readable provenance link from result metadata.

    The graph and ingestion components use different metadata names across
    existing versions, so this accepts the established aliases and returns
    ``None`` when a result has no source reference.
    """
    metadata = result.metadata or {}
    direct_link = metadata.get("provenance_url") or metadata.get("source_url")
    if direct_link:
        return str(direct_link)
    if result.entity_links:
        return str(result.entity_links[0])

    source_document = (
        metadata.get("source_document")
        or metadata.get("sourceDocument")
        or metadata.get("document")
        or metadata.get("document_name")
    )
    if not source_document:
        return None

    source_document = str(source_document)
    page = metadata.get("page_number", metadata.get("pageNumber"))
    chunk = metadata.get("chunk_id", metadata.get("sourceChunk"))
    fragment = ""
    if page is not None:
        fragment = f"#page={quote(str(page), safe='')}"
    elif chunk:
        fragment = f"#chunk={quote(str(chunk), safe='')}"

    return f"data/input/{quote(source_document, safe='')}{fragment}"


def citation_records(
    graph_results: Sequence[RetrievalResult],
    vector_results: Sequence[RetrievalResult],
) -> List[dict[str, Any]]:
    """Create stable citation records for answer and source rendering."""
    records: List[dict[str, Any]] = []
    for index, result in enumerate(graph_results, start=1):
        records.append(
            {
                "label": f"Fact {index}",
                "marker": f"[Fact {index}]",
                "source": "SPARQL/RDF graph",
                "content": result.content,
                "score": result.score,
                "provenance": provenance_link(result),
            }
        )
    for index, result in enumerate(vector_results, start=1):
        records.append(
            {
                "label": f"Chunk {index}",
                "marker": f"[Chunk {index}]",
                "source": "ChromaDB vector chunk",
                "content": result.content,
                "score": result.score,
                "provenance": provenance_link(result),
            }
        )
    return records


def alpha_for_request(router: Any, request: QueryRequest, response: HybridResponse) -> float:
    """Resolve the effective dynamic alpha used by the router."""
    return float(router._determine_alpha(request, response.query_type))


async def process_query(router: Any, request: QueryRequest) -> ChatQueryResult:
    """Run one query through the existing hybrid router and fusion pipeline."""
    response = await router.retrieve(request)
    graph_results, vector_results = split_retrieval_results(response.sources)
    alpha = alpha_for_request(router, request, response)
    return ChatQueryResult(
        request=request,
        response=response,
        graph_results=graph_results,
        vector_results=vector_results,
        alpha=alpha,
    )


def make_history_entry(result: ChatQueryResult) -> dict[str, Any]:
    """Create a session-state history entry from a completed query."""
    return QueryHistoryEntry(
        query=result.request.query,
        query_type=result.response.query_type.value,
        alpha=result.alpha,
        confidence=result.response.confidence,
        processing_time=result.response.processing_time,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        answer=result.response.answer,
    ).as_dict()


def query_suggestions(history: Sequence[Mapping[str, Any]]) -> List[str]:
    """Return recent unique queries for the chat autocomplete control."""
    suggestions: List[str] = []
    seen: set[str] = set()
    for entry in history:
        query = str(entry.get("query", "")).strip()
        if query and query not in seen:
            suggestions.append(query)
            seen.add(query)
    return suggestions
