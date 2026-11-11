"""Knowledge graph exploration helpers and Streamlit rendering.

The explorer keeps RDF loading, subgraph selection, and export generation
outside the Streamlit callback so the graph interactions remain testable. The
primary renderer is PyVis; a compact table is used when PyVis cannot load.
"""

from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from rdflib import Graph, Literal
from rdflib.namespace import RDF, RDFS

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_PATH = Path("data/graphs/approved_kg.ttl")
MAX_RENDER_NODES = 160


@dataclass(frozen=True)
class ExplorerNode:
    """A displayable node in the selected RDF subgraph."""

    node_id: str
    label: str
    kind: str
    highlighted: bool = False


@dataclass(frozen=True)
class ExplorerEdge:
    """A displayable RDF relationship."""

    source: str
    target: str
    predicate: str
    label: str


@dataclass(frozen=True)
class ExplorerSnapshot:
    """Filtered graph data used by both PyVis and static exports."""

    nodes: tuple[ExplorerNode, ...]
    edges: tuple[ExplorerEdge, ...]
    source_triples: int


def _term_id(term: Any) -> str:
    """Return a stable node ID that separates literals from resources."""
    prefix = "literal:" if isinstance(term, Literal) else "resource:"
    return prefix + str(term)


def _local_name(value: Any) -> str:
    """Return a readable local name for an RDF resource."""
    text = str(value)
    text = text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    text = text.rsplit(":", 1)[-1]
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ").strip() or text


def _label_map(graph: Graph) -> dict[str, str]:
    """Build labels once for all resources with an RDF label."""
    labels: dict[str, str] = {}
    for resource, _, label in graph.triples((None, RDFS.label, None)):
        labels[_term_id(resource)] = str(label)
    return labels


def node_label(graph: Graph, term: Any, labels: Optional[Mapping[str, str]] = None) -> str:
    """Return the best human-readable label for an RDF term."""
    if isinstance(term, Literal):
        text = str(term)
        return text if len(text) <= 72 else f"{text[:69]}…"
    labels = labels or _label_map(graph)
    return labels.get(_term_id(term), _local_name(term))


def node_type_options(graph: Graph) -> list[str]:
    """Return sorted display names for RDF classes present in the graph."""
    values = {
        node_label(graph, object_term)
        for _, _, object_term in graph.triples((None, RDF.type, None))
    }
    return sorted(value for value in values if value)


def predicate_options(graph: Graph) -> list[str]:
    """Return sorted display names for predicates present in the graph."""
    return sorted({_local_name(predicate) for _, predicate, _ in graph})


def find_matching_nodes(graph: Graph, search_term: str) -> list[str]:
    """Find resource IDs whose URI or label contains ``search_term``."""
    normalized = search_term.strip().casefold()
    if not normalized:
        return []
    labels = _label_map(graph)
    matches = set()
    for subject, _, object_term in graph:
        for term in (subject, object_term):
            term_id = _term_id(term)
            if normalized in node_label(graph, term, labels).casefold() or normalized in str(term).casefold():
                matches.add(term_id)
    return sorted(matches)


def newly_stitched_node_ids(records: Iterable[Any], graph: Graph) -> set[str]:
    """Resolve approved staging records to graph IDs for visual highlighting."""
    identifiers: set[str] = set()
    labels = _label_map(graph)
    for record in records:
        for attribute in ("subject", "object"):
            value = getattr(record, attribute, None)
            if not value:
                continue
            text = str(value)
            for subject, _, object_term in graph:
                for term in (subject, object_term):
                    if text.casefold() in node_label(graph, term, labels).casefold() or text.casefold() == str(term).casefold():
                        identifiers.add(_term_id(term))
    return identifiers


def _resource_type(graph: Graph, term: Any) -> str:
    """Classify a graph node for colors, filtering, and accessible titles."""
    if isinstance(term, Literal):
        return "literal"
    if any(str(object_term).casefold().endswith("provenance") for object_term in graph.objects(term, RDF.type)):
        return "provenance"
    if list(graph.objects(term, RDF.type)):
        return "entity"
    return "resource"


def build_snapshot(
    graph: Graph,
    *,
    search_term: str = "",
    focus_node: str = "",
    max_depth: int = 2,
    node_types: Optional[Sequence[str]] = None,
    predicates: Optional[Sequence[str]] = None,
    include_literals: bool = False,
    highlighted_nodes: Optional[set[str]] = None,
    max_nodes: int = MAX_RENDER_NODES,
) -> ExplorerSnapshot:
    """Build a bounded, filterable subgraph from an RDF graph.

    Search and focus selections define BFS roots. When no root is selected,
    the graph is shown in source order up to ``max_nodes`` so large graphs do
    not freeze the Streamlit page.
    """
    labels = _label_map(graph)
    normalized_predicates = {str(value).casefold() for value in (predicates or [])}
    normalized_types = {str(value).casefold() for value in (node_types or [])}
    highlighted_nodes = highlighted_nodes or set()

    triples = []
    adjacency: dict[str, set[str]] = {}
    all_terms: dict[str, Any] = {}
    for subject, predicate, object_term in graph:
        predicate_name = _local_name(predicate)
        if normalized_predicates and predicate_name.casefold() not in normalized_predicates:
            continue
        subject_id = _term_id(subject)
        object_id = _term_id(object_term)
        all_terms[subject_id] = subject
        all_terms[object_id] = object_term
        triples.append((subject_id, predicate_name, object_id))
        adjacency.setdefault(subject_id, set()).add(object_id)
        adjacency.setdefault(object_id, set()).add(subject_id)

    matching_ids = set(find_matching_nodes(graph, search_term))
    roots = {focus_node} if focus_node else matching_ids
    roots = {root for root in roots if root in all_terms}

    if roots:
        selected_ids = set(roots)
        frontier = set(roots)
        for _ in range(max(0, int(max_depth))):
            next_frontier = {
                neighbor
                for current in frontier
                for neighbor in adjacency.get(current, set())
                if neighbor not in selected_ids
            }
            selected_ids.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
    else:
        selected_ids = set()
        for subject_id, _, object_id in triples:
            selected_ids.update((subject_id, object_id))
            if len(selected_ids) >= max_nodes:
                break

    if not include_literals:
        selected_ids = {
            node_id for node_id in selected_ids if not node_id.startswith("literal:")
        }

    selected_ids = set(sorted(selected_ids)[: max(1, int(max_nodes))])
    nodes: list[ExplorerNode] = []
    for node_id in sorted(selected_ids, key=lambda value: node_label(graph, all_terms[value], labels).casefold()):
        term = all_terms[node_id]
        kind = _resource_type(graph, term)
        type_names = {
            node_label(graph, object_term).casefold()
            for object_term in graph.objects(term, RDF.type)
        }
        if normalized_types and not (type_names & normalized_types):
            continue
        nodes.append(
            ExplorerNode(
                node_id=node_id,
                label=node_label(graph, term, labels),
                kind=kind,
                highlighted=node_id in highlighted_nodes,
            )
        )

    visible_ids = {node.node_id for node in nodes}
    edges = tuple(
        ExplorerEdge(source=subject_id, target=object_id, predicate=predicate_name, label=predicate_name)
        for subject_id, predicate_name, object_id in triples
        if subject_id in visible_ids and object_id in visible_ids
    )
    return ExplorerSnapshot(tuple(nodes), edges, len(graph))


def snapshot_network(snapshot: ExplorerSnapshot) -> nx.MultiDiGraph:
    """Convert an explorer snapshot to a networkx graph for PyVis."""
    network = nx.MultiDiGraph()
    for node in snapshot.nodes:
        color = "#f59e0b" if node.highlighted else {
            "provenance": "#a78bfa",
            "literal": "#64748b",
            "entity": "#22d3ee",
        }.get(node.kind, "#94a3b8")
        network.add_node(
            node.node_id,
            label=node.label,
            title=f"{node.label} ({node.kind})",
            color=color,
            size=28 if node.highlighted else 20,
            shape="dot" if node.kind != "literal" else "box",
        )
    for edge in snapshot.edges:
        network.add_edge(edge.source, edge.target, label=edge.label, title=edge.label, arrows="to")
    return network


def render_pyvis_html(snapshot: ExplorerSnapshot) -> Optional[str]:
    """Render a snapshot with PyVis, returning ``None`` if unavailable."""
    try:
        from pyvis.network import Network

        network = Network(
            height="620px",
            width="100%",
            directed=True,
            bgcolor="#0e1117",
            font_color="#f8fafc",
            cdn_resources="in_line",
        )
        network.from_nx(snapshot_network(snapshot))
        network.set_options(
            json.dumps(
                {
                    "interaction": {"hover": True, "navigationButtons": True, "keyboard": True},
                    "physics": {"stabilization": {"iterations": 180}, "barnesHut": {"gravitationalConstant": -2400}},
                    "edges": {"arrows": {"to": {"enabled": True, "scaleFactor": 0.6}}, "font": {"size": 10}},
                }
            )
        )
        return network.generate_html()
    except Exception:
        logger.exception("PyVis graph rendering failed")
        return None


def _export_image(snapshot: ExplorerSnapshot, image_format: str) -> Optional[bytes]:
    """Create a dependency-light PNG or PDF snapshot with Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    width, height = 1400, 850
    image = Image.new("RGB", (width, height), "#0e1117")
    draw = ImageDraw.Draw(image)
    nodes = list(snapshot.nodes)
    positions: dict[str, tuple[int, int]] = {}
    if nodes:
        center = (width // 2, height // 2)
        radius_x, radius_y = min(520, width // 2 - 100), min(300, height // 2 - 100)
        import math

        for index, node in enumerate(nodes):
            angle = 2 * math.pi * index / max(1, len(nodes))
            positions[node.node_id] = (
                int(center[0] + radius_x * math.cos(angle)),
                int(center[1] + radius_y * math.sin(angle)),
            )
    for edge in snapshot.edges:
        if edge.source in positions and edge.target in positions:
            draw.line((*positions[edge.source], *positions[edge.target]), fill="#64748b", width=2)
    for node in nodes:
        x, y = positions[node.node_id]
        fill = "#f59e0b" if node.highlighted else "#22d3ee" if node.kind == "entity" else "#a78bfa"
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=fill)
        draw.text((x + 18, y - 8), node.label[:42], fill="#f8fafc")
    draw.text((30, 25), "The Alchemist's Chimera · Knowledge Graph Explorer", fill="#f8fafc")
    output = io.BytesIO()
    if image_format.lower() == "pdf":
        image.save(output, format="PDF", resolution=120.0)
    else:
        image.save(output, format="PNG")
    return output.getvalue()


def graph_export_bytes(snapshot: ExplorerSnapshot, image_format: str) -> Optional[bytes]:
    """Return graph image bytes for a supported export format."""
    if image_format.lower() not in {"png", "pdf"}:
        raise ValueError("Only PNG and PDF exports are supported.")
    return _export_image(snapshot, image_format)


def provenance_trail(graph: Graph, focus_ids: Sequence[str]) -> list[dict[str, str]]:
    """Return provenance-related triples touching the focused resources."""
    focus = set(focus_ids)
    rows = []
    for subject, predicate, object_term in graph:
        subject_id, object_id = _term_id(subject), _term_id(object_term)
        predicate_name = _local_name(predicate)
        is_provenance_predicate = any(
            token in predicate_name.casefold()
            for token in ("source", "evidence", "provenance", "generated", "approved", "approval", "page", "timestamp", "created")
        )
        if subject_id in focus or object_id in focus or is_provenance_predicate:
            rows.append(
                {
                    "Subject": node_label(graph, subject),
                    "Relationship": predicate_name,
                    "Object": node_label(graph, object_term),
                }
            )
    return sorted(rows, key=lambda row: (row["Subject"].casefold(), row["Relationship"].casefold()))


def timeline_events(graph: Graph) -> list[dict[str, str]]:
    """Extract dated knowledge-evolution events from RDF literals."""
    events = []
    for subject, predicate, object_term in graph:
        value = str(object_term)
        predicate_name = _local_name(predicate)
        is_dated = getattr(object_term, "datatype", None) is not None or any(
            token in predicate_name.casefold()
            for token in ("date", "time", "created", "approved", "effective")
        )
        if not isinstance(object_term, Literal) or not is_dated:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            date_text = parsed.date().isoformat()
        except ValueError:
            continue
        events.append(
            {
                "Date": date_text,
                "Entity": node_label(graph, subject),
                "Event": predicate_name,
                "Value": value,
            }
        )
    return sorted(events, key=lambda row: (row["Date"], row["Entity"], row["Event"]), reverse=True)


def resolve_graph_path(manager: Any = None) -> Path:
    """Choose the live approved graph, preferring the active staging manager."""
    candidates = []
    manager_path = getattr(manager, "approved_kg_path", None)
    if manager_path:
        candidates.append(Path(manager_path))
    candidates.extend((DEFAULT_GRAPH_PATH, Path("data/knowledge_graph.ttl"), Path("ontology/finance-ontology.ttl")))
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return candidates[0]


@lru_cache(maxsize=8)
def load_rdf_graph(path: str, modified_ns: int = 0) -> Graph:
    """Load an RDF graph, keyed by file modification time for live refresh."""
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def load_live_graph(path: Path) -> Graph:
    """Load a graph using its current modification time as a cache key."""
    modified_ns = path.stat().st_mtime_ns if path.exists() else 0
    return load_rdf_graph(str(path), modified_ns)


def _approved_records(manager: Any) -> list[Any]:
    """Read approved records from either the compatibility adapter or manager."""
    backend = getattr(manager, "comprehensive_manager", manager)
    getter = getattr(backend, "get_approved_triples", None)
    if not getter:
        return []
    try:
        return [record for _, record in getter()]
    except Exception:
        logger.exception("Unable to read approved staging records")
        return []


def render_kg_explorer(manager: Any = None) -> None:
    """Render the live, filterable, provenance-aware KG Explorer tab."""
    st.header("🗺️ Knowledge Graph Explorer")
    st.markdown(
        "Explore approved RDF facts, trace each fact back to source evidence, "
        "and inspect how the knowledge graph evolved over time."
    )

    path = resolve_graph_path(manager)
    try:
        graph = load_live_graph(path)
    except Exception as error:
        st.error(f"Knowledge graph could not be loaded from `{path}`: {error}")
        st.info("The explorer falls back to the approved graph once a valid Turtle file is available.")
        return

    labels = _label_map(graph)
    search = st.text_input(
        "Search entities or relationships",
        key="kg_search",
        placeholder="e.g., HKMA, capital adequacy, sourceDocument",
    )
    matching = find_matching_nodes(graph, search)
    focus_options = [""] + matching
    focus = st.selectbox(
        "Focus entity",
        focus_options,
        format_func=lambda value: "All graph nodes" if not value else labels.get(value, _local_name(value)),
        key="kg_focus",
    )

    controls = st.columns([1, 1, 1, 1])
    with controls[0]:
        depth = st.slider("Exploration depth", 0, 5, 2, key="kg_depth")
    with controls[1]:
        include_literals = st.checkbox("Include literal values", value=False, key="kg_literals")
    with controls[2]:
        type_filter = st.multiselect("Node type filter", node_type_options(graph), key="kg_node_types")
    with controls[3]:
        edge_filter = st.multiselect("Relationship filter", predicate_options(graph), key="kg_predicates")

    highlighted = newly_stitched_node_ids(_approved_records(manager), graph) if manager else set()
    snapshot = build_snapshot(
        graph,
        search_term=search,
        focus_node=focus,
        max_depth=depth,
        node_types=type_filter,
        predicates=edge_filter,
        include_literals=include_literals,
        highlighted_nodes=highlighted,
    )

    metrics = st.columns(4)
    metrics[0].metric("Source triples", snapshot.source_triples)
    metrics[1].metric("Visible nodes", len(snapshot.nodes))
    metrics[2].metric("Visible relationships", len(snapshot.edges))
    metrics[3].metric("Newly stitched", sum(node.highlighted for node in snapshot.nodes))

    st.subheader("🌐 Interactive subgraph")
    html = render_pyvis_html(snapshot)
    if html:
        components.html(html, height=640, scrolling=False)
    else:
        st.warning("PyVis is unavailable. Showing the selected graph as a table instead.")
        st.dataframe(
            [{"Node": node.label, "Type": node.kind, "New": node.highlighted} for node in snapshot.nodes],
            use_container_width=True,
            hide_index=True,
        )

    st.caption("Drag nodes, zoom, and hover relationships in the graph. Orange nodes were newly stitched and approved.")

    with st.expander("🔗 Provenance trail", expanded=bool(focus or search)):
        focus_ids = [focus] if focus else matching[:5]
        trail = provenance_trail(graph, [item for item in focus_ids if item])
        if trail:
            st.dataframe(trail, use_container_width=True, hide_index=True)
        else:
            st.info("Search for an entity to inspect its source document, chunk, evidence, approval, and timestamp trail.")

    with st.expander("📅 Knowledge evolution timeline"):
        events = timeline_events(graph)
        if events:
            st.dataframe(events, use_container_width=True, hide_index=True)
        else:
            st.info("No dated knowledge events were found in the approved graph.")

    st.subheader("📥 Export graph")
    export_columns = st.columns(4)
    graph_bytes = graph.serialize(format="turtle").encode("utf-8")
    with export_columns[0]:
        st.download_button("Download TTL", graph_bytes, file_name="approved_knowledge_graph.ttl", mime="text/turtle", use_container_width=True)
    with export_columns[1]:
        html_bytes = (html or "Graph renderer unavailable").encode("utf-8")
        st.download_button("Download HTML", html_bytes, file_name="knowledge_graph.html", mime="text/html", use_container_width=True)
    with export_columns[2]:
        png_bytes = graph_export_bytes(snapshot, "png")
        if png_bytes:
            st.download_button("Download PNG", png_bytes, file_name="knowledge_graph.png", mime="image/png", use_container_width=True)
        else:
            st.caption("PNG export unavailable")
    with export_columns[3]:
        pdf_bytes = graph_export_bytes(snapshot, "pdf")
        if pdf_bytes:
            st.download_button("Download PDF", pdf_bytes, file_name="knowledge_graph.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.caption("PDF export unavailable")
