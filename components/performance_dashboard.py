"""Streamlit performance dashboard for ingestion and resource monitoring."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_performance_dashboard(pipeline: Any) -> None:
    """Render current pipeline metrics, timings, limits, and pool status."""
    st.header("📈 Performance Monitor")
    if pipeline is None:
        st.info("Run a PDF ingestion to populate performance metrics.")
        return

    status = pipeline.get_status()
    metrics = status.get("metrics", {})
    performance = status.get("performance", {})
    limits = status.get("resource_limits", {})

    cards = st.columns(4)
    cards[0].metric("Chunks processed", metrics.get("processed_chunks", 0))
    cards[1].metric("Processing time", f"{metrics.get('duration_seconds', 0.0):.2f}s")
    cards[2].metric("Peak memory", f"{metrics.get('peak_memory_mb', 0.0):.1f} MB")
    cards[3].metric("Vector insertions", metrics.get("vector_insertions", 0))

    st.subheader("Stage timings")
    timings = performance.get("timings", {})
    if timings:
        st.dataframe(
            [{"stage": name, "seconds": round(value, 4)} for name, value in timings.items()],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No stage timings are available yet.")

    st.subheader("Resource limits")
    if limits:
        st.json(limits)
    else:
        st.caption("Default resource limits are active.")

    vector_store = status.get("vector_store", {})
    pool = vector_store.get("connection_pool")
    if pool:
        st.subheader("Persistent store pool")
        st.json(pool)
