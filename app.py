#!/usr/bin/env python3
"""
The Alchemist's Chimera - Streamlit Web Interface
Hybrid Graph-Vector RAG Engine with Human-in-the-Loop Governance
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import streamlit as st

from components.hybrid_chat import (
    citation_records,
    make_history_entry,
    process_query,
    provenance_link,
    query_suggestions,
)
from components.surgeons_table import render_surgeons_table
from components.kg_explorer import render_kg_explorer
from components.performance_dashboard import render_performance_dashboard
from src.config import QueryType
from src.fusion import get_fusion_engine
from src.models import QueryRequest, RetrievalResult
from src.response_generator import ResponseGenerator
from src.router import HybridRouter

# Page configuration
st.set_page_config(
    page_title="The Alchemist's Chimera",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Create necessary directories
def ensure_directories():
    """Ensure required directories exist."""
    directories = [
        "data/uploads",
        "data/tmp",
        "data/cache"
    ]
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)

# Import components
try:
    from components.sidebar import render_sidebar
    HAS_COMPONENTS = True
except ImportError:
    HAS_COMPONENTS = False
    st.warning("UI components not yet implemented. Running in minimal mode.")

# Import core components
try:
    from core.state_manager import StateManager
    from core.async_executor import AsyncExecutor
    HAS_CORE = True
except ImportError:
    HAS_CORE = False

@st.cache_resource(show_spinner=False)
def get_hybrid_router() -> HybridRouter:
    """Create the cached router used by the Hybrid Chimera Chat tab."""
    return HybridRouter(
        fusion_engine=get_fusion_engine(),
        response_generator=ResponseGenerator(),
    )


@st.cache_resource(show_spinner=False)
def get_ingestion_pipeline(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> Any:
    """Create a cached ingestion pipeline for the Surgeon’s Table."""
    from src.ingestor.pipeline import IngestionPipeline

    return IngestionPipeline(
        {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap}
    )


def _run_async(coroutine: Any) -> Any:
    """Run a router coroutine from Streamlit's synchronous execution model."""
    return asyncio.run(coroutine)


def _render_provenance(result: RetrievalResult) -> None:
    """Render a provenance link or an explicit missing-provenance notice."""
    link = provenance_link(result)
    if link:
        st.markdown(f"[Open provenance source]({link})")
    else:
        st.caption("Provenance link is not available for this result.")


def _render_source_card(result: RetrievalResult, label: str) -> None:
    """Render one graph or vector result with score and provenance."""
    metadata = result.metadata or {}
    original_score = metadata.get("original_score", result.score)
    st.markdown(f"**{label}** · relevance `{float(original_score):.2f}`")
    st.write(result.content)
    _render_provenance(result)


def _render_query_history() -> None:
    """Render recent queries and allow users to favorite or reuse them."""
    history = st.session_state.get("chat_history", [])
    with st.expander("📝 Query history and favorites", expanded=bool(history)):
        if not history:
            st.caption("Completed queries will appear here.")
            return

        for index, entry in enumerate(history):
            query = str(entry.get("query", ""))
            favorite = bool(entry.get("favorite", False))
            columns = st.columns([7, 1, 1])
            with columns[0]:
                marker = "⭐" if favorite else "▫️"
                st.markdown(
                    f"{marker} **{query}**  "
                    f"`{entry.get('query_type', 'hybrid')}` · "
                    f"α={float(entry.get('alpha', 0.5)):.2f}"
                )
            with columns[1]:
                if st.button("Use", key=f"use_query_{index}"):
                    st.session_state.chat_query = query
                    st.rerun()
            with columns[2]:
                if st.button("⭐" if favorite else "☆", key=f"favorite_query_{index}"):
                    entry["favorite"] = not favorite
                    st.rerun()


def _render_citations(result: Any) -> None:
    """Render answer citations linked to graph facts and vector chunks."""
    citations = citation_records(result.graph_results, result.vector_results)
    with st.expander("📚 Result citations", expanded=True):
        if not citations:
            st.caption("No retrieval citations were returned.")
            return
        for citation in citations:
            st.markdown(
                f"**{citation['marker']} · {citation['source']}** · "
                f"score `{float(citation['score']):.2f}`"
            )
            st.caption(citation["content"])
            if citation.get("provenance"):
                st.markdown(f"[Open source]({citation['provenance']})")


def _render_chat_result(result: Any) -> None:
    """Render the answer and transparent hybrid retrieval breakdown."""
    response = result.response
    st.subheader("🧬 Chimera answer")
    st.markdown(response.answer)

    metrics = st.columns(4)
    metrics[0].metric("Confidence", f"{response.confidence:.0%}")
    metrics[1].metric("Query type", response.query_type.value)
    metrics[2].metric("Processing time", f"{response.processing_time:.2f}s")
    metrics[3].metric("Sources", len(response.sources))

    st.subheader("⚖️ Dynamic α(t) retrieval weight")
    alpha_columns = st.columns(2)
    with alpha_columns[0]:
        st.metric("Graph weight α(t)", f"{result.alpha:.0%}")
        st.progress(result.alpha)
    with alpha_columns[1]:
        st.metric("Vector weight 1 − α(t)", f"{1 - result.alpha:.0%}")
        st.progress(1 - result.alpha)

    st.subheader("🔎 Retrieval audit")
    graph_column, vector_column = st.columns(2)
    with graph_column:
        st.markdown("#### SPARQL/RDF graph hits")
        if result.graph_results:
            for index, source in enumerate(result.graph_results, start=1):
                with st.container(border=True):
                    _render_source_card(source, f"[Fact {index}]")
        else:
            st.info("No SPARQL/RDF graph hits for this query.")
    with vector_column:
        st.markdown("#### ChromaDB vector chunks")
        if result.vector_results:
            for index, source in enumerate(result.vector_results, start=1):
                with st.container(border=True):
                    _render_source_card(source, f"[Chunk {index}]")
        else:
            st.info("No ChromaDB vector chunks for this query.")

    _render_citations(result)


def render_hybrid_chat_tab() -> None:
    """Render the Hybrid Chimera Chat query and retrieval audit interface."""
    st.header("🔍 Hybrid Chimera Chat")
    st.markdown(
        "Ask a regulatory question and inspect how deterministic graph facts "
        "and semantic document chunks contributed to the answer."
    )

    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("chat_query", "")
    st.session_state.setdefault("chat_result", None)

    suggestions = query_suggestions(st.session_state.chat_history)
    st.selectbox(
        "Query autocomplete",
        ["Choose a recent query..."] + suggestions,
        key="chat_suggestion",
        help="Choose a recent query to reuse it in the input below.",
    )
    if st.session_state.get("chat_suggestion") in suggestions:
        st.session_state.chat_query = st.session_state.chat_suggestion

    query = st.text_input(
        "Ask the Chimera",
        key="chat_query",
        placeholder="e.g. What are the capital requirements for banks under Basel III?",
        help="Enter a question about the approved knowledge graph or ingested documents.",
    )

    controls = st.columns([2, 2, 1])
    with controls[0]:
        query_type_label = st.selectbox(
            "Query strategy",
            ["Auto (dynamic)", "Entity relationship", "Regulatory", "Semantic", "Hybrid"],
            index=0,
            key="chat_query_type",
        )
    with controls[1]:
        use_dynamic_alpha = st.checkbox(
            "Use dynamic α(t)",
            value=True,
            key="chat_dynamic_alpha",
            help="Let the router select graph weight from the detected query type.",
        )
        manual_alpha = st.slider(
            "Manual graph weight α",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            disabled=use_dynamic_alpha,
            key="chat_manual_alpha",
        )
    with controls[2]:
        max_results = st.number_input(
            "Max sources",
            min_value=1,
            max_value=20,
            value=10,
            step=1,
            key="chat_max_results",
        )

    if st.button("🔍 Execute query", type="primary", use_container_width=True):
        if not query.strip():
            st.warning("Enter a query before executing the hybrid retrieval pipeline.")
        else:
            type_map = {
                "Entity relationship": QueryType.ENTITY_RELATIONSHIP,
                "Regulatory": QueryType.REGULATORY,
                "Semantic": QueryType.SEMANTIC,
                "Hybrid": QueryType.HYBRID,
            }
            request = QueryRequest(
                query=query.strip(),
                query_type=type_map.get(query_type_label),
                alpha=None if use_dynamic_alpha else manual_alpha,
                max_results=int(max_results),
                metadata={"ui": "hybrid_chimera_chat"},
            )
            with st.spinner("Running graph retrieval, vector search, fusion, and response generation..."):
                try:
                    chat_result = _run_async(process_query(get_hybrid_router(), request))
                except Exception as error:
                    st.error(f"Hybrid query failed: {error}")
                else:
                    st.session_state.chat_result = chat_result
                    st.session_state.chat_history.insert(0, make_history_entry(chat_result))
                    st.session_state.chat_history = st.session_state.chat_history[:20]
                    st.success("Query complete. Inspect the retrieval audit below.")

    if st.session_state.chat_result is not None:
        _render_chat_result(st.session_state.chat_result)
    _render_query_history()

def render_surgeons_table_tab():
    """Render the PDF ingestion and human approval interface."""
    render_surgeons_table(
        pipeline_factory=get_ingestion_pipeline,
        role=StateManager.get_role() if HAS_CORE else st.session_state.get(
            "role", "Compliance Officer (Demo)"
        ),
    )

def render_kg_explorer_tab():
    """Render the live approved knowledge graph explorer."""
    manager = st.session_state.get("surgeons_staging_manager")
    pipeline = st.session_state.get("surgeons_pipeline")
    if manager is None and pipeline is not None:
        manager = getattr(pipeline, "staging_manager", None)
    render_kg_explorer(manager=manager)

# Main application
def main():
    """Main Streamlit application."""

    # Ensure directories exist
    ensure_directories()

    # Initialize session state for tab management
    if 'current_tab' not in st.session_state:
        st.session_state.current_tab = "Hybrid Chat"

    # Render sidebar
    if HAS_COMPONENTS:
        render_sidebar()
    else:
        # Minimal sidebar
        with st.sidebar:
            st.title("🧭 Navigation")
            st.selectbox(
                "Select Your Role",
                ["Compliance Officer (Demo)", "Risk Auditor", "Regulatory Analyst"],
                index=0,
                key="role",
                help="Select your role for audit trail attribution"
            )

    # Title and description
    st.title("🧪 The Alchemist's Chimera")
    st.markdown("""
    ### Hybrid Graph-Vector RAG Engine with Human-in-the-Loop Governance

    *Powered by local LLMs, RDF knowledge graphs, and semantic search*

    **Current Role**: {} | **LLM Mode**: {}
    """.format(
        StateManager.get_role() if HAS_CORE else st.session_state.get('role', 'Compliance Officer (Demo)'),
        "Local Ollama"  # Placeholder - will be integrated from AsyncExecutor
    ))

    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🔍 Hybrid Chat", "🔬 Surgeon's Table", "🗺️ KG Explorer", "📈 Performance"]
    )
    
    with tab1:
        render_hybrid_chat_tab()
    
    with tab2:
        render_surgeons_table_tab()
    
    with tab3:
        render_kg_explorer_tab()

    with tab4:
        render_performance_dashboard(st.session_state.get("surgeons_pipeline"))

    # Footer
    st.divider()
    st.caption("The Alchemist's Chimera | Kiroween 2026 | HKMA Regulatory Compliance Demo")

if __name__ == "__main__":
    main()
