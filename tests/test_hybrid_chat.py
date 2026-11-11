"""Tests for the Hybrid Chimera Chat audit helpers."""

import asyncio
import time

from components.hybrid_chat import (
    citation_records,
    make_history_entry,
    process_query,
    provenance_link,
    query_suggestions,
    split_retrieval_results,
)
from src.config import QueryType
from src.models import QueryRequest, RetrievalResult, RetrievalSource
from src.router import HybridRouter


def test_split_retrieval_results_preserves_graph_and_vector_branches():
    """Fused results are separated for the side-by-side audit view."""
    graph_result = RetrievalResult(
        content="HKMA requires an 8% capital ratio.",
        source=RetrievalSource.HYBRID,
        score=0.7,
        entity_links=["http://example.org/finance#HKMA"],
        metadata={"original_source": "graph", "original_score": 0.9},
    )
    vector_result = RetrievalResult(
        content="A regulatory document describes capital requirements.",
        source=RetrievalSource.HYBRID,
        score=0.2,
        metadata={"original_source": "vector", "original_score": 0.8},
    )

    graph, vector = split_retrieval_results([graph_result, vector_result])

    assert graph == [graph_result]
    assert vector == [vector_result]


def test_provenance_link_supports_document_page_and_chunk_metadata():
    """Source metadata becomes a navigable local provenance link."""
    result = RetrievalResult(
        content="Evidence",
        source=RetrievalSource.GRAPH,
        score=0.9,
        metadata={
            "source_document": "HKMA policy.pdf",
            "page_number": 12,
            "chunk_id": "chunk-12",
        },
    )

    assert provenance_link(result) == "data/input/HKMA%20policy.pdf#page=12"


def test_citation_records_use_fact_and_chunk_markers():
    """The answer audit exposes stable citation markers for both branches."""
    graph_result = RetrievalResult(
        content="Graph fact",
        source=RetrievalSource.GRAPH,
        score=0.8,
        metadata={"source_url": "https://example.test/fact"},
    )
    vector_result = RetrievalResult(
        content="Vector chunk",
        source=RetrievalSource.VECTOR,
        score=0.7,
        metadata={"document": "sample.pdf", "page_number": 2},
    )

    records = citation_records([graph_result], [vector_result])

    assert [record["marker"] for record in records] == ["[Fact 1]", "[Chunk 1]"]
    assert records[0]["provenance"] == "https://example.test/fact"
    assert records[1]["provenance"] == "data/input/sample.pdf#page=2"


def test_process_query_integrates_router_and_dynamic_alpha():
    """A query uses the existing router pipeline and exposes its audit data."""
    router = HybridRouter(use_mocks=True)
    request = QueryRequest(
        query="What are the capital requirements for banks?",
        query_type=QueryType.REGULATORY,
        max_results=5,
    )

    result = asyncio.run(process_query(router, request))

    assert result.response.query_type == QueryType.REGULATORY
    assert result.alpha == 0.7
    assert result.graph_results
    assert result.vector_results
    assert result.response.sources


def test_query_history_deduplicates_autocomplete_suggestions():
    """Autocomplete shows recent unique queries in history order."""
    history = [
        {"query": "Basel III requirements"},
        {"query": "Bank subsidiaries"},
        {"query": "Basel III requirements"},
    ]

    assert query_suggestions(history) == ["Basel III requirements", "Bank subsidiaries"]


def test_history_entry_contains_query_audit_metadata():
    """Completed queries retain enough metadata for history and favorites."""
    router = HybridRouter(use_mocks=True)
    request = QueryRequest(query="Explain capital requirements")
    result = asyncio.run(process_query(router, request))

    entry = make_history_entry(result)

    assert entry["query"] == request.query
    assert entry["query_type"] == result.response.query_type.value
    assert 0.0 <= entry["alpha"] <= 1.0
    assert entry["favorite"] is False


def test_query_processing_meets_interactive_latency_target():
    """The UI helper completes a local mock query within the UI budget."""
    router = HybridRouter(use_mocks=True)
    request = QueryRequest(query="Basel III capital requirements")

    started = time.perf_counter()
    result = asyncio.run(process_query(router, request))
    elapsed = time.perf_counter() - started

    assert result.response.answer
    assert elapsed < 5.0
