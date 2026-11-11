"""Streamlit Surgeon’s Table for PDF ingestion and HITL approval.

The module keeps table transformation and bulk-operation logic separate from
Streamlit rendering so the approval workflow can be tested independently.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd
import streamlit as st

from src.ingestor.pipeline import ValidationStatus


TABLE_COLUMNS = [
    "Selected",
    "Subject",
    "Predicate",
    "Object",
    "Evidence Quote",
    "SHACL Status",
]


def save_uploaded_pdf(uploaded_file: Any, upload_dir: Path) -> Path:
    """Persist an uploaded PDF under a generated, safe filename.

    Args:
        uploaded_file: Streamlit UploadedFile-like object.
        upload_dir: Directory where the upload should be stored.

    Returns:
        The path of the persisted PDF.

    Raises:
        ValueError: If the file is not a non-empty PDF.
    """
    file_name = Path(str(getattr(uploaded_file, "name", ""))).name
    if not file_name or Path(file_name).suffix.lower() != ".pdf":
        raise ValueError("Only PDF files can be uploaded.")

    content = uploaded_file.getvalue()
    if not content:
        raise ValueError("The uploaded PDF is empty.")

    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(file_name).stem).strip("._")
    safe_stem = safe_stem or "document"
    destination = upload_dir / f"{safe_stem}_{uuid.uuid4().hex[:12]}.pdf"
    destination.write_bytes(content)
    return destination


def _backend_manager(manager: Any) -> Any:
    """Return the comprehensive manager behind the compatibility adapter."""
    return getattr(manager, "comprehensive_manager", manager)


def _validation_status(manager: Any, record_id: str, staging_triple: Any) -> str:
    """Resolve the persisted validation status for a staging record."""
    source_record = getattr(manager, "staging_records", {}).get(record_id)
    source_status = getattr(source_record, "validation_status", None)
    if source_status is not None:
        return str(getattr(source_status, "value", source_status)).upper()

    metadata = getattr(staging_triple, "metadata", {}) or {}
    metadata_status = metadata.get("validation_status") or metadata.get("classification")
    if metadata_status:
        return str(getattr(metadata_status, "value", metadata_status)).upper()

    approval_status = getattr(staging_triple, "approval_status", None)
    if str(getattr(approval_status, "value", approval_status)).lower() in {
        "approved",
        "edited_and_approved",
    }:
        return ValidationStatus.VALID.value.upper()
    return ValidationStatus.QUARANTINED.value.upper()


def _approval_status(staging_triple: Any) -> str:
    """Return a stable uppercase approval state for display and action guards."""
    status = getattr(staging_triple, "approval_status", None)
    return str(getattr(status, "value", status or "pending")).upper()


def staging_table_rows(manager: Any) -> List[Dict[str, Any]]:
    """Convert manager records into rows consumed by ``st.data_editor``.

    The internal record ID is retained for actions but hidden from the visible
    table. All required Surgeon’s Table columns use human-readable labels.
    """
    backend = _backend_manager(manager)
    records = getattr(backend, "staging_triples", {})
    rows: List[Dict[str, Any]] = []

    for record_id, staging_triple in records.items():
        rows.append(
            {
                "_record_id": record_id,
                "Selected": False,
                "Subject": str(getattr(staging_triple, "subject", "")),
                "Predicate": str(getattr(staging_triple, "predicate", "")),
                "Object": str(getattr(staging_triple, "object", "")),
                "Evidence Quote": str(getattr(staging_triple, "evidence", "")),
                "SHACL Status": _validation_status(manager, record_id, staging_triple),
                "Approval Status": _approval_status(staging_triple),
            }
        )

    return rows


def filter_and_sort_rows(
    rows: Sequence[Mapping[str, Any]],
    search_text: str = "",
    status_filter: str = "All",
    sort_column: str = "Subject",
    descending: bool = False,
) -> List[Dict[str, Any]]:
    """Filter rows by text/status and sort them for table display."""
    normalized_search = search_text.strip().lower()
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        matches_status = status_filter == "All" or row.get("SHACL Status") == status_filter
        searchable = " ".join(
            str(row.get(column, ""))
            for column in ("Subject", "Predicate", "Object", "Evidence Quote")
        ).lower()
        if matches_status and (not normalized_search or normalized_search in searchable):
            filtered.append(dict(row))

    if filtered and sort_column in filtered[0]:
        filtered.sort(
            key=lambda item: str(item.get(sort_column, "")).lower(),
            reverse=descending,
        )
    return filtered


def selected_record_ids(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    """Return selected, actionable record IDs in table order."""
    return [
        str(row["_record_id"])
        for row in rows
        if bool(row.get("Selected")) and row.get("_record_id")
    ]


def _record_snapshot(manager: Any, record_id: str) -> Optional[Dict[str, Any]]:
    """Read the editable values for one manager record."""
    staging_triple = _backend_manager(manager).staging_triples.get(record_id)
    if staging_triple is None:
        return None
    return {
        "Subject": str(getattr(staging_triple, "subject", "")),
        "Predicate": str(getattr(staging_triple, "predicate", "")),
        "Object": str(getattr(staging_triple, "object", "")),
        "Evidence Quote": str(getattr(staging_triple, "evidence", "")),
    }


def apply_table_edits(
    manager: Any,
    rows: Iterable[Mapping[str, Any]],
    reviewer: str,
    selected_only: bool = True,
) -> List[str]:
    """Persist changed editable cells through ``StagingManager.edit_triple``.

    Returns:
        Record IDs whose values changed and were persisted.
    """
    changed: List[str] = []
    for row in rows:
        record_id = str(row.get("_record_id", ""))
        if not record_id or (selected_only and not bool(row.get("Selected"))):
            continue

        current = _record_snapshot(manager, record_id)
        if current is None:
            continue
        updated = {column: str(row.get(column, "")) for column in current}
        if updated == current:
            continue

        edited = manager.edit_triple(
            record_id=record_id,
            editor=reviewer,
            subject=updated["Subject"],
            predicate=updated["Predicate"],
            object=updated["Object"],
            evidence=updated["Evidence Quote"],
        )
        if edited is not None:
            changed.append(record_id)
    return changed


def approve_records(manager: Any, record_ids: Iterable[str], reviewer: str) -> List[str]:
    """Approve selected records and return IDs accepted by the manager."""
    approved: List[str] = []
    for record_id in record_ids:
        staging_triple = _backend_manager(manager).staging_triples.get(record_id)
        if staging_triple is None or _approval_status(staging_triple) != "PENDING":
            continue
        if manager.approve_triple(record_id=record_id, reviewer=reviewer):
            approved.append(record_id)
    return approved


def reject_records(
    manager: Any,
    record_ids: Iterable[str],
    reviewer: str,
    reason: str,
) -> List[str]:
    """Reject selected records with an auditable reason."""
    rejection_reason = reason.strip() or "Rejected from Surgeon’s Table review."
    rejected: List[str] = []
    for record_id in record_ids:
        staging_triple = _backend_manager(manager).staging_triples.get(record_id)
        if staging_triple is None or _approval_status(staging_triple) != "PENDING":
            continue
        if manager.approve_triple(
            record_id=record_id,
            reviewer=reviewer,
            rejection_reason=rejection_reason,
        ):
            rejected.append(record_id)
    return rejected


def auto_approve_valid_records(manager: Any, reviewer: str = "auto_approval") -> List[str]:
    """Approve pending records whose SHACL status is ``VALID``."""
    candidates = [
        row["_record_id"]
        for row in staging_table_rows(manager)
        if row["SHACL Status"] == ValidationStatus.VALID.value.upper()
        and row["Approval Status"] == "PENDING"
    ]
    return approve_records(manager, candidates, reviewer)


def _render_pipeline_progress(metrics: Any) -> None:
    """Render final extraction metrics after synchronous pipeline processing."""
    progress = st.progress(1.0, text="Extraction complete")
    st.success(
        "Processed "
        f"{getattr(metrics, 'processed_chunks', 0)} chunks and staged "
        f"{getattr(metrics, 'total_triples', 0)} triples."
    )
    st.caption(
        "Valid: "
        f"{getattr(metrics, 'valid_triples', 0)} · Quarantined: "
        f"{getattr(metrics, 'quarantined_triples', 0)} · Duration: "
        f"{getattr(metrics, 'duration_seconds', 0.0):.2f}s"
    )
    del progress


def render_surgeons_table(
    pipeline_factory: Callable[..., Any],
    role: str,
    upload_dir: Path = Path("data/uploads"),
) -> None:
    """Render PDF upload, extraction progress, staging table, and HITL actions."""
    st.header("🔬 The Surgeon’s Table")
    st.markdown(
        "Upload a regulatory PDF, inspect grounded triples, and approve only the "
        "knowledge that should enter the live graph."
    )

    pipeline = st.session_state.get("surgeons_pipeline")
    manager = (
        getattr(pipeline, "staging_manager", None)
        if pipeline is not None
        else None
    )

    st.subheader("📤 Upload regulatory PDF")
    uploaded_file = st.file_uploader(
        "Drag and drop a PDF here, or browse for a file",
        type=["pdf"],
        key="surgeons_pdf_upload",
        help="PDF text and metadata are processed locally before staging.",
    )

    if uploaded_file is not None:
        st.info(f"Ready to process **{uploaded_file.name}**.")
        with st.expander("⚙️ Extraction settings", expanded=False):
            chunk_size = st.number_input(
                "Chunk size", min_value=500, max_value=2000, value=1000, step=100,
                key="surgeons_chunk_size",
            )
            chunk_overlap = st.number_input(
                "Chunk overlap", min_value=0, max_value=500, value=200, step=50,
                key="surgeons_chunk_overlap",
            )
            auto_approve = st.checkbox(
                "Auto-approve VALID triples after extraction",
                value=False,
                key="surgeons_auto_approve",
                help="Use the one-click action below to approve only VALID records.",
            )

        if st.button("⚗️ Start extraction", type="primary", use_container_width=True):
            try:
                document_path = save_uploaded_pdf(uploaded_file, upload_dir)
                progress = st.progress(0.05, text="Preparing PDF parser…")
                st.session_state["surgeons_progress_stage"] = "Parsing PDF"
                progress.progress(0.15, text="Parsing PDF and creating chunks…")
                pipeline = pipeline_factory(
                    chunk_size=int(chunk_size), chunk_overlap=int(chunk_overlap)
                )
                st.session_state["surgeons_progress_stage"] = "Extracting entities and triples"
                progress.progress(0.30, text="Extracting entities and grounded triples…")
                metrics = pipeline.process_pdf(document_path)
                progress.progress(0.85, text="Validating triples and updating staging…")
                st.session_state["surgeons_pipeline"] = pipeline
                manager = pipeline.staging_manager
                progress.progress(1.0, text="Extraction complete")
                st.session_state["surgeons_progress_stage"] = "Complete"
                st.success(
                    f"Processed {metrics.processed_chunks} chunks and staged "
                    f"{metrics.total_triples} triples."
                )
                st.caption(
                    f"Valid: {metrics.valid_triples} · "
                    f"Quarantined: {metrics.quarantined_triples} · "
                    f"Duration: {metrics.duration_seconds:.2f}s"
                )
                if auto_approve:
                    approved = auto_approve_valid_records(manager, reviewer=role)
                    st.info(f"Auto-approved {len(approved)} VALID triple(s).")
            except Exception as error:
                st.error(f"PDF extraction failed: {error}")

    if manager is None:
        manager = st.session_state.get("surgeons_staging_manager")
    if manager is None:
        try:
            from src.ingestor.staging_adapter import get_staging_manager

            manager = get_staging_manager(Path("data/staging"), use_comprehensive=True)
            st.session_state["surgeons_staging_manager"] = manager
        except Exception as error:
            st.warning(f"Staging records are unavailable: {error}")
            return

    rows = staging_table_rows(manager)
    if not rows:
        st.info("No triples are currently waiting in the staging area.")
        return

    st.subheader("📋 Staging triples")
    controls = st.columns([3, 2, 2, 1])
    search_text = controls[0].text_input(
        "Filter triples",
        placeholder="Search subject, predicate, object, or evidence",
        key="surgeons_filter_text",
    )
    status_filter = controls[1].selectbox(
        "SHACL status",
        ["All", "VALID", "QUARANTINED"],
        key="surgeons_status_filter",
    )
    sort_column = controls[2].selectbox(
        "Sort by",
        ["Subject", "Predicate", "Object", "SHACL Status"],
        key="surgeons_sort_column",
    )
    descending = controls[3].checkbox("Desc", key="surgeons_sort_descending")
    visible_rows = filter_and_sort_rows(
        rows, search_text, status_filter, sort_column, descending
    )

    edited_rows = st.data_editor(
        pd.DataFrame(visible_rows, columns=[
            "_record_id", *TABLE_COLUMNS, "Approval Status"
        ]),
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="surgeons_staging_editor",
        disabled=["_record_id", "SHACL Status", "Approval Status"],
        column_config={
            "_record_id": None,
            "Selected": st.column_config.CheckboxColumn("Select", default=False),
            "Evidence Quote": st.column_config.TextColumn("Evidence Quote", width="large"),
            "SHACL Status": st.column_config.TextColumn("SHACL Status"),
            "Approval Status": st.column_config.TextColumn("Approval"),
        },
    )
    editor_rows = edited_rows.to_dict("records") if hasattr(edited_rows, "to_dict") else list(edited_rows)
    selected = selected_record_ids(editor_rows)
    st.caption(f"{len(visible_rows)} shown · {len(selected)} selected · Reviewer: {role}")
    rejection_reason = st.text_input(
        "Rejection reason (used for selected records)",
        value="Rejected during HITL review.",
        key="surgeons_rejection_reason",
    )

    action_columns = st.columns(4)
    with action_columns[0]:
        if st.button("✅ Approve selected", use_container_width=True, disabled=not selected):
            apply_table_edits(manager, editor_rows, role)
            approved = approve_records(manager, selected, role)
            st.success(f"Approved {len(approved)} triple(s).")
            st.rerun()
    with action_columns[1]:
        if st.button("❌ Reject selected", use_container_width=True, disabled=not selected):
            rejected = reject_records(manager, selected, role, rejection_reason)
            st.warning(f"Rejected {len(rejected)} triple(s).")
            st.rerun()
    with action_columns[2]:
        if st.button("✏️ Save edits", use_container_width=True, disabled=not selected):
            changed = apply_table_edits(manager, editor_rows, role)
            st.success(f"Saved edits for {len(changed)} triple(s).")
            st.rerun()
    with action_columns[3]:
        if st.button("⚡ Auto-approve VALID", use_container_width=True):
            approved = auto_approve_valid_records(manager, reviewer=role)
            st.success(f"Auto-approved {len(approved)} VALID triple(s).")
            st.rerun()

    stats = manager.get_stats()
    with st.expander("📊 Staging statistics"):
        stat_columns = st.columns(3)
        stat_columns[0].metric("Total triples", stats.get("total_records", stats.get("total_triples", 0)))
        stat_columns[1].metric("Awaiting review", stats.get("pending_review", 0))
        stat_columns[2].metric("Approved", stats.get("status_counts", {}).get("valid", stats.get("status_counts", {}).get("approved", 0)))
