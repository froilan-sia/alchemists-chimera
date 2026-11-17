"""Helpers for the Hybrid Chimera Chat audit interface.

The Streamlit layer is intentionally thin. These helpers keep query result
classification, alpha calculations, provenance links, and citation formatting
independent from Streamlit so they can be tested without a running app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import re
from typing import Any, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote, urlsplit

from src.models import HybridResponse, QueryRequest, RetrievalResult, RetrievalSource


_RDF_NAMESPACES = {
    "http://example.org/finance#": "finance",
    "http://example.org/chimera#": "chimera",
    "http://alchemists-chimera.org/": "chimera",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
    "http://www.w3.org/ns/shacl#": "sh",
    "http://www.w3.org/ns/prov#": "prov",
}
_RDF_TERM_PATTERN = re.compile(
    r"https?://[^\s|<>\"']+|\b(?:finance|chimera|rdf|rdfs|owl|xsd|sh|prov):[A-Za-z_][A-Za-z0-9_.-]*\b"
)


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


def _readable_local_name(local_name: str) -> str:
    """Turn an RDF local name into a readable display label."""
    words = local_name.replace("_", " ").replace("-", " ")
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words)
    words = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", words)
    words = re.sub(r"\s+", " ", words).strip()
    return words or local_name


def format_rdf_term(term: Any) -> str:
    """Format an RDF URI or CURIE without creating a hyperlink.

    RDF and OWL identifiers are data labels in the audit panel, not web
    destinations. Known namespaces are rendered as a readable label followed
    by a compact CURIE, for example ``Basel III (finance:BaselIII)``.
    """
    value = str(term)
    if not value:
        return value

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlsplit(value)
        namespace = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        local_name = parsed.fragment or parsed.path.rsplit("/", 1)[-1]
        for uri, prefix in _RDF_NAMESPACES.items():
            if value.startswith(uri):
                local_name = value[len(uri):]
                return f"{_readable_local_name(local_name)} ({prefix}:{local_name})"
        return _readable_local_name(local_name)

    match = re.fullmatch(
        r"(?P<prefix>finance|chimera|rdf|rdfs|owl|xsd|sh|prov):(?P<local>.+)",
        value,
    )
    if match:
        local_name = match.group("local")
        return f"{_readable_local_name(local_name)} ({value})"
    return value


def format_rdf_text(text: Any) -> str:
    """Replace raw RDF/OWL identifiers in graph text with plain labels."""
    value = str(text)
    return _RDF_TERM_PATTERN.sub(lambda match: format_rdf_term(match.group(0)), value)


def display_content(result: RetrievalResult) -> str:
    """Return source content formatted for the audit panel."""
    if result.source == RetrievalSource.GRAPH or result.entity_links:
        return format_rdf_text(result.content)
    return result.content


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


def _document_endpoint_base() -> str:
    """Return the FastAPI base URL used by the Streamlit provenance links."""
    return os.getenv("DOCUMENT_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def provenance_link(result: RetrievalResult) -> Optional[str]:
    """Build a FastAPI PDF link from document provenance metadata.

    Entity links are deliberately ignored here. They identify RDF resources,
    not documents, and must never become dead ``example.org`` hyperlinks.
    """
    metadata = result.metadata or {}
    direct_link = metadata.get("provenance_url") or metadata.get("source_url")
    if direct_link:
        direct_value = str(direct_link)
        if not any(direct_value.startswith(namespace) for namespace in _RDF_NAMESPACES):
            if not direct_value.lower().split("#", 1)[0].endswith(".pdf"):
                return direct_value
            parsed = urlsplit(direct_value)
            source_document = parsed.path
            page_match = re.search(r"(?:^|&)page=(\d+)", parsed.fragment)
            if page_match:
                metadata = dict(metadata)
                metadata.setdefault("page_number", page_match.group(1))
            metadata = dict(metadata)
            metadata.setdefault("source_document", source_document)


    job_id = metadata.get("job_id") or metadata.get("source_job_id")
    source_document = (
        metadata.get("source_document")
        or metadata.get("sourceDocument")
        or metadata.get("document")
        or metadata.get("document_name")
    )
    if not job_id and source_document:
        normalized_source = str(source_document).replace("\\", "/")
        job_match = re.search(r"(?:^|/)jobs/([^/]+)/source\.pdf$", normalized_source)
        if job_match:
            job_id = job_match.group(1)
    if not source_document and not job_id:
        return None

    # The endpoint accepts a job ID and resolves it to jobs/{job_id}/source.pdf.
    # Otherwise use only the basename so metadata cannot introduce a path.
    document_key = str(job_id or source_document)
    document_key = document_key.replace("\\", "/").rsplit("/", 1)[-1]
    if not document_key:
        return None

    page = metadata.get("page_number", metadata.get("pageNumber"))
    fragment = ""
    if page is not None:
        fragment = f"#page={quote(str(page), safe='')}"
    elif metadata.get("chunk_id", metadata.get("sourceChunk")):
        chunk = metadata.get("chunk_id", metadata.get("sourceChunk"))
        fragment = f"#chunk={quote(str(chunk), safe='')}"

    return f"{_document_endpoint_base()}/documents/{quote(document_key, safe='')}{fragment}"


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
                "content": display_content(result),
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
