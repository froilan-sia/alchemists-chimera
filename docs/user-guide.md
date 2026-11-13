# User guide: The Surgeon's Table

The Surgeon's Table is the Streamlit workflow for turning a regulatory PDF into candidate knowledge-graph records and reviewing those records before or after they are written to the approved graph. It runs locally in the Streamlit process and does not call a remote ingestion API.

## Before you start

1. Install the Python dependencies from `requirements.txt`.
2. Install the spaCy model:

   ```bash
   python -m spacy download en_core_web_sm
   ```

3. Start Ollama and make the configured model available:

   ```bash
   ollama serve
   ollama pull qwen2.5:3b
   ```

4. Start Streamlit:

   ```bash
   streamlit run app.py --server.port 7860 --server.address 127.0.0.1
   ```

The Docker image performs the model setup through `start.sh` instead. See the [deployment section in the root README](https://github.com/froilan-sia/alchemists-chimera#hugging-face-spaces-deployment) for the container path.

## Select a reviewer role

The sidebar role selector offers:

- `Compliance Officer (Demo)`
- `Risk Auditor`
- `Regulatory Analyst`

The selected value is used as the reviewer string for UI edits, approvals, and rejections. These are demo roles, not an authentication or authorization system. The application currently has no login wall and does not enforce per-role permissions.

## Upload and process a PDF

1. Open the **🔬 Surgeon's Table** tab.
2. Choose a non-empty file with a `.pdf` extension. The UI writes it to `data/uploads/` under a generated safe filename.
3. Expand **Extraction settings** if you need different chunking values:
   - Chunk size defaults to `1000` characters and the UI permits `500`–`2000`.
   - Chunk overlap defaults to `200` characters and the UI permits `0`–`500`.
4. Select **Start extraction**.

The pipeline processes chunks sequentially:

1. `PDFParser` extracts page text with `pypdf` and creates chunk IDs.
2. `EntityExtractor` runs spaCy and keeps its configured entity labels.
3. `TripleExtractor` sends one chunk at a time to Ollama and parses JSON triples.
4. Evidence validation checks that each quote is at least 20 characters by default and occurs case-insensitively in the source chunk.
5. `SHACLValidator` applies basic field checks and optionally uses `pyshacl` when a shapes file is configured.
6. `ProvenanceManager` records source and extraction metadata for records that are not classified invalid.
7. The staging manager writes the record. When the chunk produces triples, the vector store also receives the chunk for later hybrid retrieval.

The progress display and final metrics show processed chunks, staged triples, valid and quarantined counts, and duration. A failure in one chunk is logged and does not stop the remaining chunks. A PDF that cannot be read at all raises a pipeline error.

### PDF limitations

The parser extracts embedded text. It does not perform OCR, so scanned/image-only pages may produce no chunks. Password-protected, malformed, or unusual PDFs may fail or produce fewer chunks than expected. Test a representative document before relying on extraction results.

## Read the staging table

The table uses the following columns:

| Column | Meaning | Editable in the UI |
| --- | --- | --- |
| `Selected` | Include the row in a bulk action. | Yes |
| `Subject` | Candidate RDF subject text. | Yes |
| `Predicate` | Candidate RDF predicate text. | Yes |
| `Object` | Candidate RDF object text. | Yes |
| `Evidence Quote` | Source text supplied by extraction. | Yes |
| `SHACL Status` | Validation classification shown by the backend. | No |
| `Approval Status` | Pending, approved, edited-and-approved, or rejected. | No |

Use the filter and sort controls to narrow the table. `SHACL Status` can be filtered to `VALID` or `QUARANTINED`. The table also shows the current reviewer role below the editor.

## Edit a record

1. Select the row.
2. Change one or more editable cells.
3. Choose **Save edits**.
4. Confirm the row reflects the saved values.
5. Review the evidence again before approval.

`StagingManager.edit_triple()` records an edit history entry containing the prior values, edited values, editor, and timestamp. Editing does not itself write the edited triple to the approved graph; approval is a separate action.

## Approve or reject records

### Approve selected

Select one or more pending records and choose **Approve selected**. The manager records the reviewer and timestamp, merges the triple and available provenance/evidence metadata into its configured approved Turtle file, and attempts to reload the graph store.

### Reject selected

Select records, enter a reason, and choose **Reject selected**. The record remains in staging with `REJECTED` status and the reviewer, timestamp, and rejection reason are retained.

### Auto-approve VALID

The button approves pending records whose displayed SHACL status is `VALID`. It uses the current sidebar role as the reviewer.

The default ingestion pipeline keeps `VALID` records pending in staging. A record enters the approved graph only after the table records an attributed reviewer decision. Direct callers that instantiate the lower-level `StagingManager` with `require_human_approval=False` retain a legacy auto-approval mode; controlled deployments should use the pipeline or pass `require_human_approval=True` explicitly.

## Where records are stored

- Uploaded PDFs: `data/uploads/`
- Staging JSON records: `data/staging/`, one file per record
- Default approved graph for the comprehensive staging manager: `data/knowledge_graph.ttl`
- Seeded explorer fallback graph: `data/graphs/approved_kg.ttl`
- ChromaDB persistence: `data/vector_store/`

The explorer prefers the active staging manager's graph path. If no manager path is available, it falls back to `data/graphs/approved_kg.ttl`, then other configured candidates. The two graph files are therefore not interchangeable by assumption. Check the path shown by `StagingManager.get_stats()` when auditing a deployment.

## Hybrid Chat after ingestion

The ingestion pipeline adds document chunks to ChromaDB even when a triple is quarantined. In **Hybrid Chimera Chat**, query the ingested content and inspect:

- the detected query type;
- graph weight `α(t)` and vector weight `1 − α(t)`;
- RDF graph facts and ChromaDB chunks in separate columns;
- source metadata and citation links when present;
- confidence and processing time.

A vector hit does not mean that its extracted triples were approved. Use the provenance and staging records to distinguish source text from approved graph facts.

## Knowledge Graph Explorer

The explorer provides:

- entity/relationship search and focus selection;
- bounded breadth-first exploration by depth;
- node-type and predicate filters;
- a provenance trail for selected nodes;
- a timeline for parseable date/time literals;
- Turtle, HTML, PNG, and PDF downloads.

Orange nodes represent records the explorer matched to approved staging records. Highlighting is a display aid; inspect the provenance trail and staging record for the audit decision.

## Operational review checklist

Before accepting an extracted fact into a controlled knowledge base, a reviewer should verify:

- the source PDF and page/chunk reference;
- the evidence quote in the source document;
- subject, predicate, and object normalization;
- validation messages and confidence;
- reviewer identity and decision timestamp;
- whether the current auto-approval behavior is acceptable for the deployment;
- backup and retention of `data/staging/`, the approved Turtle file, and ChromaDB state.

This checklist supports an audit-friendly prototype. It does not replace an institution's formal HKMA, privacy, security, model-risk, or records-management process.
