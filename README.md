---
title: The Alchemist's Chimera
emoji: 🧪
colorFrom: indigo
colorTo: slate
sdk: docker
app_port: 7860
pinned: false
---

# The Alchemist's Chimera

The Alchemist's Chimera is a local-first hybrid retrieval application for regulatory research. It combines an RDF knowledge graph with ChromaDB semantic retrieval, then exposes the two retrieval branches and their provenance in a Streamlit interface.

The project also includes a PDF-to-RDF ingestion pipeline. The pipeline extracts PDF text, anchors extraction with spaCy entities, asks a local Ollama model for candidate triples, checks evidence quotes against the source chunk, validates records, and persists them for staging and review.

> **Project status:** Alpha demonstration software. It is not an HKMA approval, an HKMA GenAI Sandbox submission, a regulatory compliance certification, or a substitute for an institution's model-risk, information-security, privacy, or records-management controls.

## Features

- **Hybrid retrieval:** graph facts from RDFLib and semantic chunks from ChromaDB are fused with a query-dependent graph weight, `α(t)`.
- **PDF ingestion API:** FastAPI accepts uploads through `POST /ingestion/jobs`, returns a job ID immediately, and exposes durable progress through `GET /ingestion/jobs/{job_id}`.
- **Baseline corpus:** PDFs under `data/input/` are SHA-256 checked and pre-indexed into ChromaDB and the baseline graph at API startup without duplicate records.
- **PDF ingestion:** `pypdf` extracts text and page metadata; configurable chunks default to 1,000 characters with 200 characters of overlap.
- **Entity anchoring:** spaCy `en_core_web_sm` filters regulatory entity types before triple extraction.
- **Local triple extraction:** Ollama calls the `qwen2.5:3b` model sequentially and expects JSON triples with evidence text.
- **Evidence validation:** extracted evidence must meet the configured minimum length and occur as a case-insensitive substring of the source chunk before the triple extractor returns it.
- **Validation and staging:** records carry extraction metadata and validation messages. The default ingestion pipeline uses the compliance staging adapter, which keeps `VALID` records pending until an attributed human reviewer approves them; quarantined records remain available for review, editing, approval, or rejection in the Surgeon’s Table.
- **Streamlit Alchemist's Lab:** three tabs cover Hybrid Chimera Chat, The Surgeon's Table, and the Knowledge Graph Explorer.
- **Graph transparency:** the chat tab shows graph hits, vector chunks, scores, citations, and the effective graph/vector weights. The explorer provides bounded subgraphs, provenance tables, timelines, and TTL/HTML/PNG/PDF exports.
- **Hugging Face Spaces container:** the Docker image starts Ollama, FastAPI on internal port `8000`, and Streamlit on public port `7860`, and prepares writable paths for the Spaces UID 1000 runtime.

## Architecture

```text
Browser ──> Streamlit UI :7860 ──┬─> FastAPI :8000
                                 │      ├─> async ingestion jobs
                                 │      ├─> baseline bootstrap
                                 │      ├─> hybrid query API
                                 │      └─> PDF provenance serving
                                 │
                                 └─> Hybrid Chat audit view

POST /ingestion/jobs ──> job queue ──> checkpointed worker
                                      ├─> pypdf chunks
                                      ├─> spaCy entities
                                      ├─> sequential Ollama triples
                                      ├─> ChromaDB chunk persistence
                                      └─> validation/staging ──> approved RDF graph

User query ──> intent router ──> RDF graph retrieval ──┐
                                      ChromaDB retrieval ─┼─> weighted fusion ─> Ollama answer
                                                        └─> citations and audit view
```

The application entry point is [`app.py`](app.py). The FastAPI service owns
baseline loading, asynchronous ingestion, query handling, and the safe
`/documents/{file_name}` PDF endpoint. The ingestion components live under
[`src/ingestor/`](src/ingestor/), the hybrid retrieval components are in
[`src/`](src/), and Streamlit rendering helpers are in [`components/`](components/).

## Requirements

- Python 3.11 or newer
- Ollama installed and available on `http://localhost:11434` for local extraction and answer generation
- Ollama model `qwen2.5:3b`
- spaCy model `en_core_web_sm`
- Enough local disk for Python dependencies, the embedding model, ChromaDB, and the Ollama model

The dependency list is in [`requirements.txt`](requirements.txt). The Dockerfile installs the same Python dependencies and downloads the spaCy model during image build.

## Local quickstart

```bash
git clone https://github.com/froilan-sia/alchemists-chimera.git
cd alchemists-chimera
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Start Ollama in a separate terminal and pull the model:

```bash
ollama serve
ollama pull qwen2.5:3b
```

Start the local application stack after Ollama is ready:

```bash
./start.sh
```

`start.sh` starts Ollama, FastAPI on `127.0.0.1:8000`, waits for
`GET /health`, and then starts Streamlit on `127.0.0.1:7860`. Open
`http://127.0.0.1:7860`. Select a role in the sidebar before reviewing staged
records. The role is written as the reviewer attribution when the UI performs
an approval, rejection, or edit.

For a manual local setup, run the backend and UI separately:

```bash
PYTHONPATH=. uvicorn src.api.main:app --host 127.0.0.1 --port 8000
streamlit run app.py --server.port 7860 --server.address 127.0.0.1
```

The API startup pre-loads baseline PDFs from `data/input/` into ChromaDB and
the baseline graph. Its interactive API documentation is available at
`http://127.0.0.1:8000/docs`.

## Using the application

### Hybrid Chimera Chat

1. Enter a regulatory question or select a previous query.
2. Leave **Use dynamic α(t)** enabled to let the router select the graph weight, or turn it off and set a manual value from 0 to 1.
3. Execute the query.
4. Review the answer, confidence, processing time, graph hits, ChromaDB chunks, and source links. **Open provenance source** serves the cited PDF through FastAPI's `/documents/{file_name}` endpoint and preserves the cited `#page=N` fragment.

The effective graph weight is shown as `α(t)`. The vector branch uses `1 − α(t)`. A source link is only shown when the result includes document, page, chunk, URL, or entity-link metadata.

### The Surgeon's Table

1. Open **The Surgeon's Table** and upload a non-empty PDF.
2. Choose chunk size and overlap if the defaults are not appropriate.
3. Start extraction. The UI submits the file to `POST /ingestion/jobs` and receives a job ID without blocking on extraction.
4. Poll `GET /ingestion/jobs/{job_id}` for monotonic stage progress, diagnostics, checkpoints, and the terminal `completed` or `partial` result.
5. Inspect the editable table. It includes selection, subject, predicate, object, evidence quote, SHACL status, and approval status.
6. Save edits before approving selected records. Use a rejection reason when rejecting records.
7. Use **Auto-approve VALID** only when that decision is acceptable for your review process.

Each processed document chunk is persisted to ChromaDB even when extraction
returns `VALID`, `QUARANTINED`, or no triples. Triple approval controls graph
publication, not vector availability.

See the full workflow in [`docs/user-guide.md`](docs/user-guide.md). The default ingestion pipeline keeps `VALID` records pending in compliance mode and requires an attributed reviewer before merging them into the live graph. The lower-level `StagingManager` retains its legacy auto-approval behavior for direct callers that use `require_human_approval=False`; controlled deployments should use the pipeline or pass `require_human_approval=True`.

### Live Knowledge Graph Explorer

The explorer loads the active graph, bounds the displayed subgraph, and supports search, focus, depth, node-type, and relationship filters. It highlights records it can match to approved staging records. It can download the current graph as Turtle, the rendered view as HTML, and the bounded snapshot as PNG or PDF.

## Data and runtime paths

| Path | Purpose |
| --- | --- |
| `data/input/` | Included fictional baseline HKMA/Basel III PDFs, pre-indexed at API startup. |
| `data/uploads/` | Direct/local upload compatibility path. |
| `data/uploads/jobs/` | Job-scoped PDFs accepted by the asynchronous FastAPI ingestion queue. |
| `data/tmp/ingestion_jobs/` | Durable ingestion job manifests and checkpoints. |
| `data/staging/` | One JSON file per staging record created by the comprehensive staging manager. |
| `data/knowledge_graph.ttl` | Default approved graph path used by the comprehensive staging manager. |
| `data/graphs/approved_kg.ttl` | Seeded sample graph and the explorer's fallback graph when no active manager path is available. |
| `data/vector_store/` | ChromaDB persistence directory for document chunks. |
| `data/tmp/` and `data/cache/` | Application runtime directories. |
| `models/` | Reserved model/data directory mounted by the local compose configuration. |

The asynchronous ingestion worker persists each processed chunk to ChromaDB
regardless of whether it produces `VALID`, `QUARANTINED`, or no triples. Triple
extraction is sequential per worker to keep Ollama resource usage bounded; the
job queue, checkpoint files, and API status endpoints keep uploads non-blocking.
The default `IngestionPipeline` configuration uses the local Ollama URL,
`qwen2.5:3b`, `data/vector_store`, and `data/staging`.

## Hugging Face Spaces deployment

This repository is configured as a **Docker Space**, not a standard Streamlit Space. The YAML front matter at the top of this README sets `sdk: docker` and `app_port: 7860`, matching the port exposed by [`Dockerfile`](Dockerfile). Hugging Face documents the Docker Space configuration and port setting in its [Docker Spaces guide](https://huggingface.co/docs/hub/spaces-sdks-docker) and [configuration reference](https://huggingface.co/docs/hub/spaces-config-reference).

### Create the Space

1. Create a new Hugging Face Space and choose **Docker** as the SDK.
2. Push this repository to the Space, or connect the repository as the Space source.
3. Keep the root `README.md`, `Dockerfile`, `start.sh`, `requirements.txt`, `app.py`, `src/`, `components/`, `data/`, and `ontology/` in the Space repository.
4. Select hardware with enough CPU, memory, and disk for the Python dependencies, spaCy, sentence-transformers, ChromaDB, and `qwen2.5:3b`. The free CPU tier may be slow or run out of disk during the first build/model pull.
5. Wait for the image build. The Dockerfile installs Ollama and Python dependencies and downloads `en_core_web_sm` during the build.

### Runtime startup

`start.sh` performs the following startup sequence:

1. Creates writable runtime paths under `/app`.
2. Starts `ollama serve` on the internal loopback address.
3. Waits for `/api/tags` to report readiness.
4. Pulls `qwen2.5:3b` unless it is already listed by Ollama.
5. Starts `uvicorn src.api.main:app --host 127.0.0.1 --port 8000`.
6. Waits for FastAPI `GET /health` before launching Streamlit.
7. FastAPI pre-loads `data/input/` baseline documents and starts the async
   ingestion worker before Streamlit accepts browser traffic.
8. Starts `streamlit run /app/app.py --server.port=7860 --server.address=0.0.0.0`.
9. Monitors all services and shuts the container down if a required service exits.

FastAPI handles `POST /ingestion/jobs`, `GET /ingestion/jobs/{job_id}`, query
requests, and `/documents/{file_name}` provenance serving. The public Space
origin exposes Streamlit on port `7860`; provenance links therefore use a
same-origin `/documents/{file_name}#page=N` URL when `SPACE_HOST` is set.
The image sets `OLLAMA_MODELS=/app/.ollama/models` and `HF_HOME=/app/.cache`, and creates the directories with permissions suitable for the Spaces UID 1000 container runtime. You can override startup values with Space variables such as `OLLAMA_MODEL`, `OLLAMA_STARTUP_TIMEOUT`, `STREAMLIT_PORT`, or `STREAMLIT_ADDRESS`; keep the public Streamlit port at `7860` unless the Space metadata and deployment plan are changed together.

The first build and first startup require network access to install/download dependencies and retrieve the Ollama model. Runtime inference is local to the container after the model is available. This is local-first operation, not a claim that the public Space is air-gapped.

### Persistence and health checks

The Dockerfile creates `/app/data`, `/app/models`, `/app/.ollama/models`, and `/app/.cache`, but a normal Space restart can discard files written inside the container. Hugging Face's Docker documentation describes this persistence limitation and the available [Storage Bucket](https://huggingface.co/docs/hub/storage-buckets) option. Attach storage or use another approved persistence strategy before treating staged or approved data as durable.

The Docker image health check probes Streamlit's `http://localhost:7860/_stcore/health` endpoint. This is a container readiness check, not a business-level validation of Ollama, the graph, or the vector store.

For local FastAPI development, use [`docker-compose.yml`](docker-compose.yml). It intentionally overrides the Dockerfile command and exposes FastAPI on port `8000`; it is not the Hugging Face Spaces startup path.

## HKMA GenAI Sandbox and ART governance notes

The design follows governance ideas that are useful for a controlled prototype:

- **Accountability:** the sidebar role selector attributes UI actions to a named demo role; staging records retain reviewer, timestamp, edit history, and rejection reason fields.
- **Transparency:** the system keeps source chunk/page metadata, evidence text, extraction status, validation messages, graph/vector retrieval branches, scores, and answer citations.
- **Human control:** the default pipeline leaves `VALID` records pending until the Surgeon’s Table records an attributed reviewer decision. The table exposes edit, reject, approve, and explicitly reviewer-triggered auto-approve actions. Direct lower-level `StagingManager` callers retain a legacy `require_human_approval=False` mode, which is not the controlled default.
- **Resilience:** the triple extractor retries failed Ollama calls with exponential backoff; the pipeline continues to the next PDF chunk after an individual chunk error; the staging manager has transaction rollback support for approval operations.
- **Deterministic checks:** evidence substring checks and basic/optional SHACL validation run before records are classified. Configure a shapes file explicitly when the application needs the repository's full SHACL shapes rather than the validator's built-in fallback shapes.

These controls are implementation features, not proof of compliance. Before regulated use, perform a formal risk assessment, privacy and data-classification review, security review, model validation, access-control review, retention review, and operational acceptance process. Read the HKMA's [Generative A.I. Sandbox arrangement](https://www.hkma.gov.hk/media/eng/doc/key-information/guidelines-and-circular/2024/20240920e1a1.pdf) and its [ART Framework announcement](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2026/10/20261015-3/) alongside the institution's own policies.

## API and developer documentation

- [Surgeon's Table and HITL user guide](docs/user-guide.md)
- [Python ingestion and staging APIs](docs/api.md)
- [Troubleshooting guide](docs/troubleshooting.md)
- [Contribution guide](CONTRIBUTING.md)
- [Sample data notes](data/input/SAMPLE_DATA_README.md)
- [Ingestion component README](src/ingestor/README.md)

The repository includes a FastAPI backend for asynchronous PDF ingestion, hybrid queries, health checks, and provenance serving. Upload a PDF with `POST /ingestion/jobs`, poll `GET /ingestion/jobs/{job_id}`, and open cited PDFs through `/documents/{file_name}#page=N`. The backend pre-loads baseline documents from `data/input/` during startup.

## Validation and examples

Run the focused tests and checks from the repository root:

```bash
pytest -q
python -m compileall -q examples
mkdocs build --strict
```

The example runner in [`examples/pipeline_usage.py`](examples/pipeline_usage.py) initializes local NLP, Ollama, vector, and staging components. Compile it before running it in automation, and run it only when those services and dependencies are intentionally available. It is not a network-free smoke test.

## Contributing

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a change. Keep documentation claims tied to the current code, add or update tests for behavior changes, and do not commit secrets, private regulatory documents, generated model caches, ChromaDB state, or user-uploaded PDFs.

## License

This project is released under the [MIT License](LICENSE).

## Links

- Repository: https://github.com/froilan-sia/alchemists-chimera
- Kiro: https://kiro.dev/docs
- RDFLib: https://rdflib.readthedocs.io/
- ChromaDB: https://docs.trychroma.com/
- Ollama: https://github.com/ollama/ollama
- spaCy: https://spacy.io/usage/models
- SHACL: https://www.w3.org/TR/shacl/
- Hugging Face Docker Spaces: https://huggingface.co/docs/hub/spaces-sdks-docker

Built with Kiro for Kiroween 2026.
