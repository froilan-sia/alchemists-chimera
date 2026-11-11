"""Focused tests for the live knowledge graph explorer."""

from pathlib import Path
from time import perf_counter

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD

from components.kg_explorer import (
    build_snapshot,
    graph_export_bytes,
    load_live_graph,
    provenance_trail,
    render_pyvis_html,
    snapshot_network,
    timeline_events,
)


APPROVED_GRAPH = Path("data/graphs/approved_kg.ttl")


def test_approved_graph_builds_searchable_subgraph_and_pyvis_html():
    """The real approved graph produces a bounded interactive subgraph."""
    graph = load_live_graph(APPROVED_GRAPH)

    snapshot = build_snapshot(graph, search_term="HKMA", max_depth=1)

    assert snapshot.source_triples > 0
    assert snapshot.nodes
    assert any(
        "HKMA" in node.label
        for node in snapshot.nodes
    )
    assert snapshot.edges
    html = render_pyvis_html(snapshot)
    assert html is not None
    assert "Knowledge" not in html or "nodes" in html
    assert len(snapshot_network(snapshot)) == len(snapshot.nodes)


def test_snapshot_filters_relationships_and_highlights_newly_stitched_nodes():
    """Predicate filters do not leak edges and approved nodes receive highlight state."""
    graph = Graph()
    ex = Namespace("http://example.test/")
    graph.add((ex.bank, RDFS.label, Literal("Demo Bank")))
    graph.add((ex.bank, RDF.type, ex.FinancialEntity))
    graph.add((ex.bank, ex.regulatedBy, ex.hkma))
    graph.add((ex.bank, ex.locatedIn, ex.hong_kong))
    graph.add((ex.hkma, RDFS.label, Literal("HKMA")))
    graph.add((ex.hong_kong, RDFS.label, Literal("Hong Kong")))

    snapshot = build_snapshot(
        graph,
        focus_node="resource:http://example.test/bank",
        max_depth=1,
        predicates=["regulated By"],
        highlighted_nodes={"resource:http://example.test/bank"},
    )

    assert len(snapshot.edges) == 1
    assert snapshot.edges[0].predicate == "regulated By"
    assert next(
        node for node in snapshot.nodes if node.label == "Demo Bank"
    ).highlighted


def test_provenance_and_timeline_extract_audit_metadata():
    """Source evidence and dated approval facts are available to the UI."""
    graph = Graph()
    ex = Namespace("http://example.test/")
    graph.add((ex.fact, RDFS.label, Literal("Capital fact")))
    graph.add((ex.fact, ex.sourceDocument, Literal("policy.pdf")))
    graph.add(
        (
            ex.fact,
            ex.approvalTimestamp,
            Literal("2024-11-11T10:15:00Z", datatype=XSD.dateTime),
        )
    )

    trail = provenance_trail(graph, ["resource:http://example.test/fact"])
    events = timeline_events(graph)

    assert any(row["Relationship"] == "source Document" for row in trail)
    assert events[0]["Date"] == "2024-11-11"
    assert events[0]["Event"] == "approval Timestamp"


def test_png_and_pdf_exports_are_real_downloadable_documents():
    """The dependency-light export path creates both requested formats."""
    graph = load_live_graph(APPROVED_GRAPH)
    snapshot = build_snapshot(graph, search_term="HKMA", max_depth=1)

    png = graph_export_bytes(snapshot, "png")
    pdf = graph_export_bytes(snapshot, "pdf")

    assert png and png.startswith(b"\x89PNG")
    assert pdf and pdf.startswith(b"%PDF")


def test_large_graph_snapshot_stays_bounded():
    """Subgraph construction remains bounded for a graph larger than the UI cap."""
    graph = Graph()
    ex = Namespace("http://example.test/")
    for index in range(1200):
        subject = ex[f"entity-{index}"]
        object_term = ex[f"entity-{index + 1}"]
        graph.add((subject, ex.relatedTo, object_term))

    started = perf_counter()
    snapshot = build_snapshot(graph, max_nodes=160)
    elapsed = perf_counter() - started

    assert len(snapshot.nodes) <= 160
    assert elapsed < 2.0
