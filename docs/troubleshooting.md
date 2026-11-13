# Troubleshooting

## The app cannot load `en_core_web_sm`

The entity extractor loads the spaCy model during pipeline construction. Install it into the same Python environment that runs Streamlit or the Docker image:

```bash
python -m spacy download en_core_web_sm
python -c 'import spacy; print(spacy.load("en_core_web_sm").meta["name"])'
```

If the error occurs in a Space, rebuild the image so the Dockerfile's model-download layer runs again. Check the build logs for network or disk errors.

## Ollama is unavailable

For local development, check that the service responds:

```bash
curl http://127.0.0.1:11434/api/tags
ollama list
ollama pull qwen2.5:3b
```

The default client URL is `http://localhost:11434`. Pass `ollama_base_url` in an `IngestionPipeline` configuration when using another local address. The triple extractor retries failed requests, but the application still needs a reachable Ollama service and an available model.

In a Hugging Face Space, inspect `startup.log` and `ollama.log` under `/app`. `start.sh` waits for Ollama readiness and pulls `qwen2.5:3b` unless it is already cached. A failed pull stops startup instead of launching a partially working UI.

## Hugging Face startup times out

The first build downloads Python packages and the spaCy model. The first runtime startup may also download the Ollama model. Check:

- Space hardware has sufficient disk, memory, and CPU;
- the Space can reach package and model registries during build/startup;
- `OLLAMA_STARTUP_TIMEOUT` is long enough for the selected hardware;
- `/app/.ollama/models` and `/app/.cache` are writable by UID 1000;
- the Space metadata still declares `sdk: docker` and `app_port: 7860`.

The container health check probes `http://localhost:7860/_stcore/health`; it does not prove that an Ollama model is loaded.

## Uploaded PDFs produce no chunks

`pypdf` extracts embedded text but does not OCR scanned pages. Try a text-based PDF and inspect the parser directly:

```python
from pathlib import Path
from src.ingestor.pdf_parser import PDFParser

chunks = PDFParser().parse_pdf(Path("data/input/your-document.pdf"))
print(len(chunks), chunks[0].text[:200] if chunks else "no text")
```

A corrupt, password-protected, or unusual PDF may also produce a parser error or skipped pages. The parser logs page-level failures and continues where possible.

## Few triples are returned

This can be expected. The extractor only returns records with the required JSON fields, acceptable confidence, and evidence that is at least 20 characters by default and appears in the same chunk. Check the source text, entity extraction, Ollama response logs, and chunk size.

To inspect the intermediate stages:

```python
from src.ingestor.pipeline import create_default_pipeline

pipeline = create_default_pipeline()
chunks = pipeline.pdf_parser.parse_pdf("data/input/your-document.pdf")
entities = pipeline.entity_extractor.extract_entities(chunks[0].text, chunks[0].id)
triples, status = pipeline.triple_extractor.extract_triples_from_chunk(chunks[0], entities)
print(status, len(entities), len(triples))
```

## Records are quarantined or validation is unexpected

The validator performs basic required-field, confidence, and evidence checks. Full `ontology/shapes.ttl` validation is only used when a shapes file is passed to `SHACLValidator` or the pipeline configuration. The Streamlit pipeline factory currently does not pass that file and therefore uses the built-in fallback/basic validation.

Inspect the validation messages stored with the staging record. Do not edit a record merely to force a `VALID` status; confirm the subject, predicate, object, and evidence against the source PDF first.

## I cannot find the approved graph

The current code uses more than one graph path:

- the comprehensive staging manager defaults to `data/knowledge_graph.ttl`;
- the seeded sample graph is `data/graphs/approved_kg.ttl`;
- the explorer uses the active manager path when available and otherwise falls back to the seeded graph.

Use `manager.get_stats()` or `pipeline.staging_manager.get_stats()` to inspect `approved_kg_path` and `staging_path`. If you need one canonical path for a deployment, pass and verify that path in the staging manager configuration and update the explorer integration accordingly.

## VALID records remain pending for human review

The default ingestion pipeline uses the compliance staging adapter, which constructs the comprehensive manager with `require_human_approval=True`. `VALID` records remain in staging until the UI records an attributed reviewer decision. If a direct caller intentionally uses the lower-level `StagingManager` with `require_human_approval=False`, its legacy auto-approval behavior is expected; use the pipeline or pass `require_human_approval=True` for controlled data.

## The graph reload does not show a new fact

After approval, the manager attempts to reload the graph store. Check:

1. The approval call returned `True`.
2. The configured approved Turtle path exists and parses.
3. The graph store points to the same file or configured ontology path.
4. The Streamlit explorer cache was refreshed by a file modification time change.
5. The fact is not hidden by search, focus, type, relationship, or depth filters.

A successful file merge does not guarantee that an unrelated graph-store instance is using the same path.

## ChromaDB insertion fails or retrieval is empty

Check that `data/vector_store/` is writable and that the process has enough disk. The ingestion pipeline calls `VectorStore.add_documents()` for each processed chunk that produces triples. The vector store uses a persistent ChromaDB collection named `documents`.

If the collection contains stale or duplicate data from test runs, use an isolated `vector_store_path` in a temporary pipeline configuration rather than deleting shared application data. The project does not automatically clean or compact user data.

## The FastAPI service does not start

The FastAPI service is separate from Streamlit. Start it with:

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

For Docker Compose, use `docker compose up app`; the compose file overrides the image command and maps port `8000`. The Hugging Face Space uses `start.sh` and Streamlit on `7860`, so do not use the compose command as the Space startup command.

## Data disappeared after a Space restart

Files written inside a normal Docker Space container may be lost on restart. The Dockerfile creates writable directories but does not make them durable. Attach an approved Hugging Face storage option or export/backup staging JSON, the approved Turtle graph, and ChromaDB data before restarting. Never treat the public demo Space as the system of record.

## How to collect useful diagnostics

Capture:

- Python version and installed dependency versions;
- whether `en_core_web_sm` loads;
- `curl http://localhost:11434/api/tags` output without secrets;
- pipeline `get_status()` output;
- staging `get_stats()` output;
- the relevant Streamlit, `startup.log`, or `ollama.log` excerpt;
- PDF page count and whether the PDF contains selectable text.

Remove document contents, credentials, private identifiers, and uploaded regulatory material before sharing logs in an issue.
