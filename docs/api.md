# API reference

This page documents the interfaces implemented in the repository. The PDF ingestion workflow is currently exposed through Python classes and the Streamlit UI. There is no public FastAPI endpoint for uploading or processing a PDF.

## Ingestion pipeline

Import the pipeline from `src.ingestor.pipeline`:

```python
from pathlib import Path
from src.ingestor.pipeline import IngestionPipeline, create_default_pipeline

pipeline = create_default_pipeline()
metrics = pipeline.process_pdf(Path("data/input/hkma_capital_requirements.pdf"))
print(metrics.total_triples, metrics.valid_triples, metrics.quarantined_triples)
```

### `IngestionPipeline(config=None)`

`config` is an optional dictionary. The implemented defaults are:

| Key | Default | Meaning |
| --- | --- | --- |
| `chunk_size` | `1000` | PDF chunk size in characters. |
| `chunk_overlap` | `200` | Character overlap between chunks. |
| `entity_types` | `ORG`, `PERSON`, `LAW`, `MONEY`, `GPE` | spaCy labels passed to the entity extractor. |
| `min_entity_confidence` | `0.5` | Entity confidence threshold used by the extractor. |
| `ollama_base_url` | `http://localhost:11434` | Ollama HTTP base URL. |
| `model_name` | `qwen2.5:3b` | Ollama model name. |
| `confidence_threshold` | `0.5` | Triple confidence threshold configuration. |
| `base_uri` | `http://alchemists-chimera.org/` | Base URI used by provenance helpers. |
| `vector_store_path` | `./data/vector_store` | ChromaDB persistence directory. |
| `staging_path` | `./data/staging` | Per-record JSON staging directory. |
| `shapes_file` | `None` | Optional SHACL Turtle file. With `None`, the validator uses its built-in fallback shapes/basic checks. |

The constructor initializes the PDF parser, spaCy extractor, Ollama triple extractor, provenance manager, SHACL validator, ChromaDB vector store, and compatibility staging manager. Initialization therefore requires the spaCy model and the Python dependencies even before a PDF is processed.

### `process_pdf(pdf_path)`

`process_pdf()` accepts a string or `pathlib.Path` and returns a `PipelineMetrics` dataclass. It raises `FileNotFoundError` for a missing path and wraps an overall failure in `PipelineError`. A page-level parsing error is logged and the parser continues to the next page where possible. A chunk-level processing error increments `failed_chunks` and the pipeline continues with later chunks.

`PipelineMetrics` exposes:

- `total_chunks`
- `processed_chunks`
- `failed_chunks`
- `total_triples`
- `valid_triples`
- `quarantined_triples`
- `vector_insertions`
- `start_time` and `end_time`
- `processing_times`
- calculated `success_rate`, `validation_rate`, and `duration_seconds` properties

### `get_status()` and `reset()`

`get_status()` returns a dictionary containing pipeline status, metrics, staging statistics, and the vector-store health response. `reset()` clears in-memory pipeline metrics and returns the pipeline status to `pending`; it does not delete staging files, the approved graph, or ChromaDB data.

## PDF parser

Import from `src.ingestor.pdf_parser`:

```python
from pathlib import Path
from src.ingestor.pdf_parser import PDFParser, PDFParserConfig

parser = PDFParser(PDFParserConfig(chunk_size=800, chunk_overlap=100))
chunks = parser.parse_pdf(Path("data/input/basel_iii_framework.pdf"))
for chunk in chunks:
    print(chunk.id, chunk.page_number, chunk.text[:80])
```

### `PDFParserConfig`

- `chunk_size`: 100–5000 characters, default `1000`.
- `chunk_overlap`: 0–500 characters, default `200`.
- `remove_extra_whitespace`: default `True`.
- `include_page_numbers`: default `True`.
- `max_pages`: optional page limit.

`PDFParser.parse_pdf()` returns `PDFChunk` objects with `id`, `text`, `page_number`, `chunk_index`, `total_chunks`, `metadata`, character offsets, `document_id`, and `document_name`. `parse_pdf_streaming()` is also available when callers need a generator.

## Entity extractor

Import from `src.ingestor.entity_extractor`:

```python
from src.ingestor.entity_extractor import EntityExtractor, EntityExtractorConfig

extractor = EntityExtractor(
    EntityExtractorConfig(entity_types=["ORG", "LAW", "MONEY"])
)
entities = extractor.extract_entities("HKMA published the Basel III requirements.", "chunk-1")
```

`EntityExtractor` loads the configured spaCy model during construction. The default model is `en_core_web_sm`. `extract_entities(text, chunk_id=None)` returns `ExtractedEntity` records with source text, entity type, character offsets, confidence, context, normalized text, and metadata. The extractor filters labels using `EntityExtractorConfig.entity_types`, applies `min_confidence`, and can deduplicate results.

## Triple extractor

Import from `src.ingestor.triple_extractor`:

```python
from src.ingestor.triple_extractor import TripleExtractor

triples, status = pipeline.triple_extractor.extract_triples_from_chunk(
    chunk, entities
)
```

`TripleExtractorConfig` includes:

- `ollama_base_url`: default `http://localhost:11434`;
- `model_name`: default `qwen2.5:3b`;
- `max_tokens`: default `2048`;
- `temperature`: default `0.1`;
- `max_retries`: default `3` with exponential backoff;
- `timeout_seconds`: default `30`;
- `max_triples_per_chunk`: default `10`;
- `min_evidence_length`: default `20`;
- `confidence_threshold`: default `0.5`;
- `fallback_predicate`: default `chimera:relatedTo`.

`extract_triples_from_chunk()` returns `(list[ExtractedTriple], ExtractionStatus)`. The response parser requires `subject`, `predicate`, `object`, `evidence`, and `confidence`. It discards records with invalid JSON, missing fields, low/empty evidence, or evidence that is not a case-insensitive substring of the original chunk. Ollama calls are sequential at pipeline level.

`ExtractedTriple` uses the field name `evidence`, not `evidence_quote`, and includes `confidence`, `chunk_id`, `entity_anchors`, `metadata`, and `extraction_timestamp`. Its `to_json()` and `to_turtle()` helpers are available for serialization.

## Provenance manager

Import from `src.ingestor.provenance_manager`:

```python
from src.ingestor.provenance_manager import ProvenanceManager

manager = ProvenanceManager()
uri = manager.normalize_to_uri("Bank of America")
record = manager.create_provenance_record(triple, chunk, entities)
```

The manager creates normalized subject/predicate/object identifiers, full subject/predicate/object URIs, provenance and triple identifiers, provenance records, RDF provenance graphs, Turtle serialization, chain validation, and export packages. `normalize_to_uri()` returns a normalized identifier such as `entity_bank_of_america`; `create_subject_uri()`, `create_predicate_uri()`, and `create_object_uri()` turn those values into full URIs using the configured base URI. The exact URI format differs from the `chimera:` example used in the design draft.

`create_provenance_record()` connects an extracted triple to the source chunk, page/document metadata supplied by the parser, extraction method, and timestamp. The pipeline creates records for valid and quarantined classifications, not for records classified invalid.

## SHACL validator

Import from `src.ingestor.shacl_validator`:

```python
from pathlib import Path
from src.ingestor.shacl_validator import SHACLValidator

validator = SHACLValidator(Path("ontology/shapes.ttl"))
classification, messages = validator.validate_and_classify(triple)
```

The validator always performs basic required-field, confidence, and evidence checks. If `pyshacl` is installed and a shapes graph can be loaded, it also performs SHACL validation. `validate_triple()` returns `(is_valid, messages)`, `batch_validate()` validates a list, and `validate_and_classify()` returns a classification string such as `valid`, `quarantined`, or `invalid` plus messages.

The Streamlit factory currently constructs the pipeline without `shapes_file`, so it uses the validator's built-in fallback/basic validation. To use `ontology/shapes.ttl` from Python, pass `{"shapes_file": "ontology/shapes.ttl"}` in the pipeline configuration and verify that the shapes match the extracted triple model.

## Staging manager

The compatibility factory used by the UI is:

```python
from pathlib import Path
from src.ingestor.staging_adapter import get_staging_manager

manager = get_staging_manager(Path("data/staging"), use_comprehensive=True)
stats = manager.get_stats()
```

The comprehensive backend in `src/staging_manager.py` provides:

- `add_triple_for_staging(...)` for persistence;
- `get_pending_review()`;
- `get_approved_triples()`;
- `get_rejected_triples()`;
- `approve_triple(record_id, reviewer, edited_triple=None, rejection_reason=None)`;
- `edit_triple(record_id, editor, subject=None, predicate=None, object=None, evidence=None, confidence=None)`;
- `get_stats()`;
- `reset_staging(include_approved=False)`;
- `export_approved_kg(output_path=None)`.

The adapter additionally exposes the compatibility methods used by the pipeline and Streamlit components. `approve_triple()` merges approved data into the configured Turtle file, adds approval/evidence metadata, and attempts a live graph reload. The default pipeline constructs the adapter in human-approval mode, so `VALID` records remain pending until an attributed reviewer calls `approve_triple()`. Direct lower-level `StagingManager` callers can retain legacy auto-approval by using `require_human_approval=False`; controlled callers should pass `True`.

## FastAPI query service

Run the optional API with:

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Available routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service information and feature flags. |
| `GET` | `/health` | Component status response. |
| `POST` | `/query` | Accepts the `QueryRequest` JSON model and returns `HybridResponse`. |
| `GET` | `/query/simple` | Query-string convenience wrapper with `q`, optional `query_type`, `alpha`, and `max_results`. |
| `GET` | `/metrics` | Placeholder metrics response. |
| `GET` | `/docs` | FastAPI Swagger UI. |
| `GET` | `/redoc` | FastAPI ReDoc UI. |

Example request:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H 'content-type: application/json' \
  -d '{"query":"What are the capital requirements under Basel III?","max_results":10}'
```

`QueryRequest` validates `alpha` between 0 and 1 and `max_results` between 1 and 100. `HybridResponse` includes `answer`, `sources`, `confidence`, `query_type`, `processing_time`, and `timestamp`. The API does not currently expose the Streamlit staging actions or PDF upload route.
