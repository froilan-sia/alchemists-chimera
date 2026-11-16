# pdf-stream-extraction-failure Bugfix Design

## Overview

This design addresses the uploaded-PDF ingestion timeout defect represented by requirement 2.11 in `bugfix.md`. The current Surgeon’s Table upload path writes the Streamlit upload to disk and then calls `IngestionPipeline.process_pdf()` synchronously. PDF parsing, spaCy entity extraction, Ollama requests, SHACL validation, vector writes, and staging writes all occur before the caller receives a final result. A slow or large document therefore keeps the frontend request busy, provides no durable status contract, and can leave the caller without a useful diagnostic when processing fails.

The fix introduces a local asynchronous ingestion-job boundary. The upload request validates and durably spools the uploaded byte stream, creates a job, and returns a `job_id` with HTTP 202. A bounded background runner processes the source incrementally. Callers poll `GET /ingestion/jobs/{job_id}` until a terminal state, render the returned progress, and display diagnostic errors. The existing pipeline remains the extraction authority, but it gains a progress/event seam, job-scoped checkpoints, byte-stream source support, and idempotent incremental persistence.

The design is based on the repository paths that currently implement the flow:

- `components/surgeons_table.py`: `save_uploaded_pdf()` persists `UploadedFile.getvalue()` and `render_surgeons_table()` calls `pipeline.process_pdf()` synchronously.
- `app.py`: `get_ingestion_pipeline()` supplies the cached pipeline used by the Streamlit tab.
- `src/ingestor/pdf_parser.py`: `PDFParser.parse_pdf_streaming()` yields page-local chunks from a filesystem `Path`; `pypdf.PdfReader` still requires a seekable source.
- `src/ingestor/pipeline.py`: `IngestionPipeline.process_pdf()` consumes parser chunks, preprocesses entities in a bounded thread pool, calls the triple extractor sequentially, and writes checkpoint state after batches.
- `src/ingestor/triple_extractor.py`: Ollama calls use blocking `requests`, retries, and a configured request timeout.
- `src/staging_manager.py` and `src/ingestor/staging_adapter.py`: staging records are persisted one at a time, while approved graph publication remains a separate human-review action.
- `src/vector_store.py`: Chroma persistence is already wrapped by a bounded connection pool and accepts stable document IDs in the normal implementation.
- `src/api/main.py`: query and health routes exist, but there is currently no upload or ingestion-status endpoint.
- `tests/integration/test_ingestion_pipeline.py`, `tests/unit/test_task18_resilience.py`, `tests/unit/test_performance_optimization.py`, and `tests/test_surgeons_table.py`: direct pipeline, failure, bounded-processing, upload-helper, and staging behavior are already covered but do not exercise an asynchronous upload/status contract.

### Scope boundary

This design covers parsing and extracting from bytes supplied by an uploaded PDF. It does not design or change PDF generation, PDF export/download, document rendering, watermarking, company disclaimers, or project-document metadata validation. Those are separate concerns and are not used as acceptance criteria for this ingestion timeout fix. In particular, an uploaded PDF is an input byte stream that is spooled for `pypdf`; it is never regenerated or exported by this workflow.

## Glossary

- **Bug_Condition (C)**: An accepted uploaded PDF job whose caller waits for synchronous extraction, cannot observe durable progress, or cannot retrieve a diagnostic terminal failure.
- **Property (P)**: Every accepted job exposes a stable status resource that progresses to completion or failure, reports counters and stage, and includes a safe diagnostic when processing fails.
- **Preservation**: Existing extraction semantics remain unchanged: page text is chunked with configured overlap, evidence grounding and SHACL classification still run, vector chunks are stored, candidate triples remain in staging, and approval is still a separate HITL action.
- **Uploaded byte stream**: Bytes received from a multipart upload. The bytes are validated and copied to a safe local spool file or seekable temporary stream before `pypdf` reads them.
- **PDF generation/export**: Any operation that creates a new PDF or produces a PDF download. It is outside this design.
- **Ingestion job**: A durable local record identified by `job_id` that tracks one uploaded source and one extraction run.
- **Job status endpoint**: `GET /ingestion/jobs/{job_id}`, the source of truth used by frontend callers and automated upload tests after the asynchronous submission.
- **Diagnostic**: A structured, user-safe error containing a stable code, stage, message, retryability, and optional non-sensitive details.
- **Incremental persistence**: Persisting each completed chunk’s vectors, staging results, and checkpoint before proceeding to later chunks.
- **Chunk concurrency**: The number of chunk tasks that may be active in the asynchronous runner. This is bounded independently from the LLM concurrency limit.
- **LLM concurrency**: The number of simultaneous Ollama requests. It remains one by default to preserve the current sequential inference behavior and local-resource safeguards.

## Bug Details

### Observed implementation and defect

The current upload path has several timeout and observability gaps:

1. `save_uploaded_pdf()` calls `uploaded_file.getvalue()`, so the entire upload is materialized before processing and only filename extension and non-empty content are checked.
2. `render_surgeons_table()` calls `pipeline.process_pdf(document_path)` inside the Streamlit button callback. The callback does not submit a job or poll an endpoint.
3. `PDFParser.parse_pdf_streaming()` is generator-based but accepts only a `Path`. It yields chunks incrementally, yet the caller has no API-visible progress while the generator and downstream stages run.
4. `ResourceLimiter.check()` is called while chunks are consumed, but blocking work inside a chunk, including a `requests` call with retries, cannot update a status endpoint and may outlast the caller’s request budget.
5. Checkpoint state is currently associated with a pipeline checkpoint path rather than a job-specific manifest. A concurrent or interrupted upload can therefore lack an isolated status and recovery record.
6. Vector insertion is batched after chunk processing and staging records are written during triple processing. This provides useful persistence, but the upload caller cannot tell which stage or chunk has completed.
7. `src/api/main.py` has no upload route. A future asynchronous route would therefore have no existing client contract to enforce, and current frontend/test code would need explicit migration rather than silently treating `job_id` as final metrics.

### Bug Condition

The bug manifests when a valid or invalid PDF is submitted through an upload caller and extraction takes long enough that synchronous processing blocks the caller, or when the caller receives an asynchronous `job_id` but does not poll the status resource. The defective behavior is the absence of a durable, observable lifecycle ending in either a successful result or a diagnostic failure.

**Formal Specification:**

```text
FUNCTION isBugCondition(input)
  INPUT: input of type UploadedPdfRequest and caller behavior
  OUTPUT: boolean

  accepted := input has a PDF upload accepted for processing
  synchronous_wait := caller waits for parse/extraction/persistence before returning
  missing_status := no stable GET status resource exists for input.job_id
  unpolled_job := caller receives input.job_id but does not poll until terminal state
  opaque_failure := processing fails and caller cannot retrieve a structured diagnostic

  RETURN accepted AND (
      synchronous_wait
      OR missing_status
      OR unpolled_job
      OR opaque_failure
  )
END FUNCTION
```

### Concrete examples

- **Large or slow upload**: A regulatory PDF produces many chunks and several Ollama retries. The current Streamlit callback remains inside `process_pdf()` until all chunks finish, so the UI cannot show the actual stage or completed-chunk count while the work runs. Under the new contract, the upload returns `202` immediately and the UI displays `parsing`, `extracting`, and `persisting` progress from the status endpoint.
- **Malformed uploaded bytes**: `save_uploaded_pdf()` accepts non-empty bytes with a `.pdf` name. `pypdf` later raises while the synchronous callback is active. Under the new contract, the upload request can return a job, and the job status reaches `failed` with a diagnostic such as `PDF_PARSE_FAILED` and the stage `parsing`.
- **Ollama timeout**: A chunk exhausts the configured request retries. The current pipeline returns fallback triples or records a chunk failure, but the caller has no job-level status describing which chunk failed and whether the run completed partially. The new status records `failed_chunks`, a retryable diagnostic when applicable, and a terminal `partial` or `failed` state according to the policy below.
- **Compatibility mistake**: A refactored upload route returns `{ "job_id": "..." }`, while an existing caller still expects `metrics.total_triples`. The caller stops before extraction completes and never shows the eventual error. Every upload caller and upload test must instead submit, poll, and interpret the terminal status schema.
- **Incremental recovery**: A process interruption occurs after chunks 1–4 have been vectorized and staged. A job-scoped checkpoint records those stable chunk IDs. A retry resumes from chunk 5, and idempotent writes prevent duplicate vector or staging records if chunk 4 is replayed.

## Expected Behavior

### Upload and status API schemas

The API should expose a multipart upload route and a status route. The upload route must not return final extraction metrics because extraction is asynchronous.

**Submission:** `POST /ingestion/jobs`

- Request: multipart field `file`; optional form fields `chunk_size`, `chunk_overlap`, and a bounded configuration profile.
- Validation: safe filename, `.pdf` extension, maximum byte size, non-empty stream, and a `%PDF-` header check before the job is queued. Full parse validation still occurs in the worker.
- Success: HTTP `202 Accepted`.
- Response shape:

```json
{
  "job_id": "ing-01J...",
  "status": "queued",
  "status_url": "/ingestion/jobs/ing-01J...",
  "source": {
    "file_name": "regulatory-policy.pdf",
    "size_bytes": 184320,
    "content_sha256": "..."
  },
  "created_at": "2026-11-16T12:00:00Z"
}
```

**Status:** `GET /ingestion/jobs/{job_id}`

```json
{
  "job_id": "ing-01J...",
  "status": "running",
  "stage": "extracting_triples",
  "progress": {
    "fraction": 0.47,
    "pages_processed": 38,
    "pages_total": 80,
    "chunks_discovered": 61,
    "chunks_processed": 48,
    "chunks_failed": 1,
    "triples_extracted": 117,
    "triples_staged": 112,
    "vector_chunks_persisted": 48
  },
  "diagnostics": [
    {
      "code": "CHUNK_EXTRACTION_RETRY",
      "stage": "extracting_triples",
      "message": "Chunk 49 timed out after the configured retries; processing continued.",
      "retryable": true,
      "chunk_id": "doc-page039-chunk000"
    }
  ],
  "result": null,
  "created_at": "2026-11-16T12:00:00Z",
  "started_at": "2026-11-16T12:00:02Z",
  "updated_at": "2026-11-16T12:04:10Z",
  "completed_at": null
}
```

For a terminal successful or partial job, `result` contains the serializable subset of `PipelineMetrics` and the persisted document/staging identifiers. It must include `total_chunks`, `processed_chunks`, `failed_chunks`, `total_triples`, `valid_triples`, `quarantined_triples`, `vector_insertions`, and `duration_seconds`. For a failed job, `result` may be partial but `diagnostics` must contain at least one non-sensitive terminal diagnostic.

Status values are `queued`, `running`, `completed`, `partial`, `failed`, and `canceled`. `completed`, `partial`, `failed`, and `canceled` are terminal. `progress.fraction` is monotonic from 0 to 1 for normal completion; a failed job may stop below 1. Counts are monotonic and never decrease during one job.

### Job lifecycle

```text
POST upload
  -> validate and spool bytes
  -> create queued job manifest
  -> return 202 with job_id
  -> runner claims job
  -> running / parsing
  -> running / extracting_entities
  -> running / extracting_triples
  -> running / validating_and_staging
  -> running / persisting_vectors
  -> finalizing
  -> completed       (all chunks processed)
     or partial      (document parsed, but one or more chunks failed)
     or failed       (fatal upload, parse, resource, or persistence failure)
     or canceled     (only if cancellation is added in the same API)
```

State transitions must be validated and written atomically. A terminal state is immutable except for adding a recovery note. A missing job returns HTTP 404. A failure after HTTP 202 is represented by the status resource, not as a later HTTP 500 from the original upload request.

### Preservation requirements

**Unchanged extraction behavior:**

- The current page text extraction and configurable character chunking remain the source of `PDFChunk` values. The default `chunk_size=1000` and `chunk_overlap=200` remain unchanged.
- Page-level parser failures continue to be recorded as warnings and skipped where the existing parser can continue. A PDF that cannot be opened or parsed at all remains a fatal job failure.
- Entity extraction, evidence grounding, SHACL classification, provenance creation, triple fallback behavior, and staging semantics remain unchanged unless a diagnostic or progress callback is added around them.
- Valid and quarantined candidates remain in controlled staging. The job does not auto-publish candidates to the approved graph merely because processing became asynchronous.
- Vector persistence continues to attach document, page, chunk, and source metadata and uses stable chunk IDs where supported.
- Direct callers of `IngestionPipeline.process_pdf(Path)` retain a synchronous compatibility wrapper and receive `PipelineMetrics`; they do not receive a `job_id` unless they use the new job service explicitly.

**Caller migration requirement:**

- `render_surgeons_table()` must submit the uploaded file to the asynchronous ingestion API/client, retain the returned `job_id`, poll the status endpoint until `completed`, `partial`, `failed`, or `canceled`, render progress while polling, and render every terminal diagnostic.
- Automated tests that exercise upload submission or frontend upload behavior must use the same submit-and-poll contract. They must not assert final triples immediately after the `202` response.
- Existing direct parser, pipeline, staging, and helper unit tests may remain direct tests because they do not act as upload callers. They must continue to cover the synchronous compatibility path and the underlying extraction semantics.

### Polling behavior

The frontend client should poll immediately once, then use a bounded interval such as 250 ms for the first few polls and 1–2 seconds thereafter, with a configurable maximum wait only for UI safety. A client-side wait limit must not mark the server job failed; it should show that polling stopped and retain the `job_id` for retry. Each poll updates `st.progress`, the current stage, counters, and diagnostics. On terminal failure or partial completion, the UI must show the diagnostic code and message rather than only a generic exception string.

## Hypothesized Root Cause

1. **Synchronous UI orchestration**: The Streamlit callback directly invokes `process_pdf()`, so all parsing and model work occupies the UI execution turn.
2. **No asynchronous API boundary**: `src/api/main.py` has no upload or job-status route, so there is no durable contract for long-running work or a way for callers to observe progress.
3. **Blocking downstream stages**: `PDFParser` and the pipeline are synchronous, and `TripleExtractor` uses blocking `requests` with retries. The current parser generator reduces retained PDF chunks but does not make execution non-blocking.
4. **Insufficient job isolation**: Checkpoint state is stored through the pipeline’s configured checkpoint path rather than a job-specific manifest. Concurrent uploads can share state unless the new job runner supplies isolated paths.
5. **Late and incomplete observability**: Metrics are available after `process_pdf()` returns, while page/chunk events are logged rather than persisted in a status record. Parser warnings and extractor failures are therefore difficult for a frontend caller to surface.
6. **Non-idempotent staging identity**: `StagingManager.add_triple_for_staging()` generates a time-based record ID. Replaying a chunk after an interruption can create duplicate staging records unless the job coordinator records a durable write ledger or the staging contract gains an idempotency key.
7. **Upload buffering and validation gap**: `getvalue()` loads all upload bytes and checks only extension/non-empty content. This increases memory pressure and defers malformed-PDF feedback until after processing starts.

## Correctness Properties

Property 1: Bug Condition - Uploaded ingestion becomes observable and non-blocking

_For any_ accepted uploaded PDF where `isBugCondition(input)` returns true, the fixed upload flow SHALL return a `job_id` and status URL without waiting for extraction to finish, and the status endpoint SHALL expose monotonic stage/progress information until a terminal completion or failure state; any failure SHALL include at least one structured diagnostic with a stage, stable code, and user-safe message.

**Validates: Requirements 2.11**

Property 2: Preservation - Extraction and non-upload caller behavior

_For any_ input where the upload/status bug condition does NOT hold, the fixed implementation SHALL preserve the existing PDFChunk, extraction, validation, vector, staging, and `process_pdf(Path)` compatibility behavior, and non-upload callers SHALL not be required to interpret a `job_id`.

**Validates: Requirements 2.11**

Property 3: Incremental persistence and replay safety

_For any_ job that is interrupted after any completed chunk boundary, resuming or replaying the job SHALL preserve all successfully persisted chunk results without duplicate stable vector entries or duplicate job-scoped staging entries, and SHALL continue from the durable checkpoint when the source hash and configuration match.

**Validates: Requirements 2.11**

Property 4: Bounded asynchronous execution

_For any_ number of accepted jobs and generated chunks, the runner SHALL never exceed configured job, chunk, entity-preprocessing, LLM, or persistence concurrency limits, and a slow chunk SHALL not prevent status updates for unrelated queued or completed work.

**Validates: Requirements 2.11**

## Fix Implementation

### Components and responsibilities

The implementation should add narrow components rather than put job orchestration into the FastAPI route or Streamlit renderer.

1. **`src/ingestor/upload_store.py` — `UploadedPdfStore`**
   - Read multipart bytes in bounded blocks from FastAPI’s `UploadFile` rather than calling `getvalue()` for the complete file.
   - Enforce maximum upload bytes, safe generated filenames, disk-space failures, and an initial `%PDF-` signature check.
   - Store the source under a job-specific directory such as `data/uploads/jobs/{job_id}/source.pdf` using an atomic temporary-file rename.
   - Compute SHA-256 while copying so the job manifest can identify the exact source.
   - Expose a seekable file path or `SpooledTemporaryFile` to the parser. `pypdf` still needs random access; this is byte-stream ingestion with bounded upload buffering, not a claim that `pypdf` can parse a non-seekable socket directly.
   - Delete the source only after retention policy allows it. Keep it through retry/recovery and include only the path-independent filename/hash in status responses.

2. **`src/ingestor/job_store.py` — `IngestionJobStore`**
   - Persist one JSON manifest per job under `data/tmp/ingestion_jobs/{job_id}/status.json` with atomic replace and a file lock or process-local lock.
   - Store lifecycle state, source metadata, configuration, counters, stage, timestamps, diagnostics, result metrics, and completed chunk IDs.
   - Validate state transitions and use compare-and-set semantics when claiming queued jobs.
   - Keep an append-only diagnostic/event log for troubleshooting without exposing stack traces to the frontend.
   - On startup, mark stale `running` jobs as `failed` with `JOB_WORKER_INTERRUPTED` or place them in a recoverable queue when the source and checkpoint are intact.

3. **`src/ingestor/job_runner.py` — `AsyncIngestionJobRunner`**
   - Accept jobs from the API, claim them from `IngestionJobStore`, and execute work outside the request handler.
   - Use an `asyncio.Queue(maxsize=N)` for pending jobs, a job semaphore for total active jobs, and explicit task ownership so the runner can shut down cleanly.
   - Run existing synchronous parser, spaCy, Ollama, Chroma, and staging operations with `asyncio.to_thread()` or a bounded executor. Never call blocking component methods directly on the event loop.
   - Emit status updates after source validation, parser page progress, each chunk completion, each diagnostic, each persistence step, and finalization.

4. **`src/ingestor/pdf_parser.py` — seekable source and progress seam**
   - Preserve `parse_pdf(Path)` and `parse_pdf_streaming(Path)` for compatibility.
   - Add a source abstraction accepting a seekable binary stream plus `document_name` and optional source hash, or centralize path opening in a helper that supports both `Path` and the job’s spooled file.
   - Pass a progress callback/event sink that reports `pages_processed`, `pages_total`, and chunks discovered without changing chunk text, IDs, overlap, or page warning behavior.
   - Do not use a PDF writer or export path in this component.

5. **`src/ingestor/pipeline.py` — reusable core and incremental hooks**
   - Extract the body of `process_pdf()` into a source-oriented internal method that accepts a parser source, job context, progress sink, checkpoint, and persistence coordinator.
   - Retain `process_pdf(Path)` as a synchronous wrapper around that core for examples and direct callers.
   - Move checkpoint location from one shared default file to a job-specific path while allowing the compatibility wrapper to retain its existing configured behavior.
   - Publish metrics after each chunk rather than only when the whole method returns.
   - Preserve the existing `PipelineStatus` meanings for direct callers and map them to the job status values at the job boundary.

6. **`src/ingestor/incremental_persistence.py` — `IncrementalPersistenceCoordinator`**
   - Upsert vector text with the stable `PDFChunk.id`, metadata, and job/source identifiers. Keep the existing fallback for injected stores that do not accept `ids`.
   - Stage each valid/quarantined candidate using a deterministic idempotency key based on source hash, chunk ID, triple index/content fingerprint, and extraction configuration. If changing the staging manager API is undesirable, maintain this key in the job manifest before calling the existing manager and skip already-recorded keys on replay.
   - Write the chunk checkpoint only after required vector and staging writes succeed. Record a per-step failure when a write is incomplete.
   - Keep approved graph publication out of ingestion. Existing reviewer actions still call `StagingManager.approve_triple()` and its transactional graph merge.

7. **`src/models.py` or a new `src/ingestor/job_models.py` — API contracts**
   - Define Pydantic models for `JobSubmissionResponse`, `JobProgress`, `JobDiagnostic`, `JobResult`, and `IngestionJobStatus`.
   - Use enums for lifecycle and stage names, `Field(ge=0, le=1)` for progress fraction, and default factories for lists/dictionaries.
   - Serialize timestamps as timezone-aware ISO-8601 values. Do not include exception tracebacks, local absolute paths, uploaded content, or Ollama prompts in public status.

8. **`src/api/main.py` — upload and polling routes**
   - Add `POST /ingestion/jobs` that validates/spools the upload, creates the manifest, enqueues the job, and returns `202`.
   - Add `GET /ingestion/jobs/{job_id}` that reads the manifest and returns the status schema.
   - Return `400` for invalid form/configuration, `413` for size limits, `415` for a non-PDF upload, `404` for an unknown job, and `503` only when the runner cannot accept new work. Processing errors after acceptance remain in the status body.
   - Initialize and stop the runner in application lifespan rather than relying on a request-created background task that can disappear when a worker exits.

9. **`components/surgeons_table.py` and `app.py` — caller migration**
   - Replace the direct `pipeline.process_pdf()` call in `render_surgeons_table()` with an upload client that submits the saved/spooled PDF and polls the status URL.
   - Render the server’s stage and counters in the existing progress UI. Keep `surgeons_progress_stage`, `surgeons_pipeline`, and staging-manager loading compatible with the existing table actions; after completion, load the job’s configured staging manager rather than assuming the request-local pipeline finished in the UI turn.
   - Display all returned diagnostics with their message and stage. Use a generic fallback only when the status resource itself cannot be read.
   - Keep the upload helper’s safe filename behavior and existing UI settings. The helper may remain useful for a local compatibility client, but the API client must not depend on `getvalue()` for unbounded buffering.

### Bounded asyncio concurrency

The runner should apply separate limits because the repository has different safe concurrency characteristics:

```text
job_semaphore       = configured max active ingestion jobs
chunk_semaphore     = configured max active chunk tasks per job
entity_semaphore    = configured max spaCy preprocessing tasks
llm_semaphore       = 1 by default; preserves sequential Ollama inference
persistence_lock    = serialized per-job writes, with the existing store pool underneath
```

A parser producer yields chunks into a bounded queue. A fixed number of async workers consumes that queue. Each worker calls synchronous extraction code through `asyncio.to_thread()` and wraps the operation in a component timeout. Triple extraction is protected by `llm_semaphore=1`, so adding asynchronous job/status support does not turn the current Ollama path into unbounded parallel inference. Entity preprocessing may overlap up to its configured limit, matching the current bounded `ThreadPoolExecutor` behavior. Persistence is performed in stable chunk order or under a per-job lock to make checkpoints deterministic.

`asyncio.wait_for()` should enforce job-stage and chunk deadlines, while the underlying Ollama request keeps its existing HTTP timeout and retry settings. Cancellation must prevent a timed-out result from being committed. Because a thread already executing synchronous code cannot always be force-killed, the implementation must keep executor capacity bounded and ensure late results are discarded by job generation/checkpoint checks.

### Incremental chunking and progress calculation

- Spool the uploaded bytes first, then open the seekable source once for `PdfReader`.
- Discover total pages before iteration when `pypdf` exposes it. Do not materialize all `PDFChunk` objects.
- Preserve `_process_page()` chunk boundaries and overlap. A chunk ID remains the stable identity for vector and checkpoint writes.
- After each page, publish parser progress. After each chunk, publish extraction, validation, staging, and vector counters.
- Calculate progress from weighted stages when total pages/chunks are known. If total chunks are unknown, expose `chunks_discovered` and a bounded stage fraction rather than inventing a precise percentage. Set `fraction=1` only for successful finalization.
- A chunk that yields no triples can still count as processed and its vector text can be persisted, matching current behavior.
- A page warning is included in `diagnostics` but does not by itself fail the job. A fatal reader error, source I/O error, resource-limit error, or unrecoverable persistence error fails the job.

### Error and retry policy

Use stable diagnostic codes and retain detailed stack traces only in server logs/audit files:

| Code | Stage | Terminal | Behavior |
| --- | --- | --- | --- |
| `UPLOAD_EMPTY` / `UPLOAD_TOO_LARGE` / `UPLOAD_NOT_PDF` | `upload` | yes, before queue | Reject the submission with 400, 413, or 415. |
| `PDF_PARSE_FAILED` | `parsing` | yes | Mark `failed`; retain source/checkpoint for diagnosis or retry. |
| `PDF_PAGE_SKIPPED` | `parsing` | no | Add warning and continue to later pages. |
| `CHUNK_TIMEOUT` | extraction stage | no by default | Mark the chunk failed, continue if the job remains within limits, and finish as `partial`. |
| `OLLAMA_UNAVAILABLE` | `extracting_triples` | no by default | Preserve existing fallback/deferred behavior; add a retryable diagnostic. |
| `RESOURCE_LIMIT_EXCEEDED` | runner | yes | Stop safely, persist completed chunks, and mark `failed` or `partial` according to whether any useful result was committed. |
| `PERSISTENCE_FAILED` | persistence | yes | Do not mark the chunk complete; retain checkpoint and diagnostic for retry. |
| `JOB_WORKER_INTERRUPTED` | runner | yes/recoverable | Mark stale jobs on startup and allow explicit retry from the durable checkpoint. |

The status response must distinguish a warning from a terminal error. The UI must show warnings as progress diagnostics and terminal errors as actionable failure messages. Diagnostic messages must never include uploaded text, prompts, secrets, absolute local paths, or raw exception traces.

### Compatibility migration plan

1. Introduce the job models, upload store, job store, runner, and API routes without removing `process_pdf(Path)`.
2. Add the source/progress/persistence seams to the pipeline while keeping existing direct method signatures and enum values.
3. Migrate `render_surgeons_table()` to submit and poll. Its tests should inject an upload/status client so the Streamlit test seam does not require a running external server.
4. Add API integration tests that use `TestClient` or an ASGI transport: submit a PDF, assert `202` and `job_id`, repeatedly call the status endpoint, and assert a terminal result or diagnostic. The helper must poll, not sleep once and assume completion.
5. Keep `tests/integration/test_ingestion_pipeline.py` as direct core-pipeline coverage. Add a separate asynchronous upload test module so direct pipeline tests are not incorrectly treated as API callers.
6. Update examples and `docs/api.md` to distinguish the asynchronous upload API from the synchronous compatibility method. Existing scripts using `process_pdf(Path)` continue to work during migration.
7. Remove the compatibility wrapper only in a later, separately approved breaking-change specification. This bugfix must not require unrelated caller changes.

## Testing Strategy

### Validation approach

Testing follows the bug-condition methodology: first establish that the current upload path blocks and lacks a status contract, then verify the new job boundary, and finally compare extraction behavior and persistence outcomes with the existing direct pipeline. Tests should use fake parser, entity, Ollama, vector, and staging components for timing and failure cases; only a small number of integration tests should use real `pypdf` and isolated temporary stores.

### Exploratory bug-condition checking

Run before implementation or against a branch containing only the current code:

1. Exercise `render_surgeons_table()` with a pipeline double whose `process_pdf()` blocks on an event. Confirm that no job ID/status resource or intermediate progress is available and the callback cannot render terminal diagnostics until the call returns.
2. Submit malformed non-empty `%PDF`-absent bytes through the current upload helper and pipeline seam. Confirm that extension/non-empty validation passes and parse failure occurs later inside synchronous processing.
3. Exercise a slow triple extractor with a request timeout/retry delay. Confirm that `process_pdf()` provides no externally pollable progress during the blocking operation.
4. Simulate an exception after a chunk has been staged or vectorized. Confirm that the current shared checkpoint and random staging ID behavior do not provide a job-scoped idempotency contract.

Expected counterexamples are a blocked UI turn, no status URL, no durable completed-chunk counter, or an exception that reaches only the generic UI error path.

### Fix checking

**Goal:** Verify requirement 2.11 for every accepted uploaded job.

**Pseudocode:**

```text
FOR ALL accepted_uploads DO
  submission := POST /ingestion/jobs with accepted_uploads.bytes
  ASSERT submission.status_code == 202
  ASSERT submission.job_id is present

  REPEAT
    status := GET /ingestion/jobs/{submission.job_id}
    ASSERT status.progress.fraction is within [0, 1]
    ASSERT status.progress counters never decrease
    ASSERT status.stage is valid
    ASSERT status.diagnostics are structured and safe
  UNTIL status.status IN {completed, partial, failed, canceled}

  ASSERT status.status is terminal
  IF status.status IN {failed, partial} THEN
    ASSERT status.diagnostics contains a code, stage, and message
  END IF
END FOR
```

### Preservation checking

**Goal:** Verify that asynchronous orchestration does not change the existing extraction contract.

**Pseudocode:**

```text
FOR ALL representative PDFs and injected component outcomes DO
  direct_result := IngestionPipeline.process_pdf(Path(source))
  async_result := submit_and_poll_status(source)

  ASSERT async_result terminal result preserves chunking and metrics semantics
  ASSERT stable chunk IDs and source metadata are preserved
  ASSERT grounded triples reach the same validation/staging categories
  ASSERT vector chunks are persisted with the same content and metadata
  ASSERT approved graph is unchanged until a reviewer calls approval
END FOR
```

### Unit tests

- **Upload spooling and validation**: bounded block copying, safe names, SHA-256, empty/oversized/non-PDF rejection, atomic rename, and cleanup behavior.
- **Byte-stream parser**: a seekable `BytesIO`/spooled source produces the same `PDFChunk` text, page numbers, overlap, IDs, and page warnings as the existing path parser; malformed bytes produce `PDF_PARSE_FAILED` diagnostics.
- **Job models/store**: schema validation, valid/invalid state transitions, atomic status writes, monotonic counters, terminal immutability, 404 lookup, and stale-worker recovery.
- **Runner lifecycle**: queued-to-terminal transitions, immediate submission return, stage events, per-job checkpoint paths, worker shutdown, and diagnostic redaction.
- **Bounded concurrency**: instrument fake entity/triple/persistence components and assert active counts never exceed configured semaphores. Assert LLM active count remains one by default.
- **Timeouts and retries**: slow parser/chunk/Ollama/store doubles produce the correct non-terminal or terminal diagnostic and do not commit a timed-out chunk.
- **Incremental persistence**: failure after each persistence step, checkpoint resume, stable vector upsert, staging idempotency keys, and no duplicate writes on replay.
- **Compatibility wrapper**: `process_pdf(Path)` still returns `PipelineMetrics`, retains direct error types, and uses the same core extraction behavior.
- **Streamlit caller seam**: a fake status client is polled until each terminal state; progress text/counters and every diagnostic are rendered; the caller does not treat `job_id` as final metrics.

### Property-based tests

Use Hypothesis for generated scenarios rather than fixed sleeps:

- Generate bounded sequences of chunks and inject a failure at any chunk/stage. Assert that completed chunk IDs are a prefix or explicit replay-safe set, counters are monotonic, and terminal status is reached with a diagnostic when appropriate.
- Generate job counts, chunk counts, and semaphore configurations within valid limits. Assert maximum active jobs/chunks/entities/LLM calls never exceeds configuration.
- Generate valid/invalid byte prefixes and filenames. Assert upload validation returns only the documented acceptance or rejection class and never starts a worker for rejected input.
- Generate repeated poll responses with delayed completion/failure. Assert the frontend poller continues until a terminal status, surfaces progress, and surfaces diagnostic messages.
- Generate equivalent path and spooled-byte sources for the same fixture PDF. Assert stable chunk text, IDs, metadata, and extraction classification.

### Integration tests

- **Asynchronous API completion**: upload a small real PDF through `TestClient`, assert HTTP 202, poll `GET /ingestion/jobs/{job_id}`, and assert `completed` with metrics, vector persistence, and staged records.
- **Asynchronous API failure**: upload corrupt or unsupported bytes, poll until `failed`, and assert a structured parse diagnostic is visible without an HTTP 500 from the original submission.
- **Partial extraction**: inject one timed-out/failing chunk, poll to `partial`, and assert successful chunks remain searchable/staged while the failed chunk diagnostic is present.
- **Frontend migration**: exercise the Surgeon’s Table upload client against the ASGI app or an injected endpoint client and assert progress updates, terminal state handling, staging manager availability, and diagnostic rendering.
- **Restart/recovery**: stop the runner after a persisted chunk, restart it, recover the job manifest, and assert replay does not duplicate vectors or staging entries.
- **Direct compatibility regression**: run the existing integration pipeline tests and compare their metrics/status expectations with the new internal core implementation.

No application source code is modified as part of this design phase. The implementation phase should make the source changes listed above and then run the existing suite plus the new API, polling, concurrency, persistence, and recovery tests.
