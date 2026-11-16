# Implementation Plan

## Overview

This plan fixes the uploaded-PDF ingestion timeout and observability defect using the approved bug-condition design. It follows the required exploratory sequence: establish the missing asynchronous contract on the unfixed flow, record preservation behavior, implement the fix in the specified incremental source order, migrate every upload caller, and validate the full polling, persistence, recovery, and compatibility behavior.

The implementation order for application changes is fixed:

1. Core job contracts and storage.
2. Pipeline seams and incremental persistence.
3. Async runner and FastAPI routes.
4. Caller migration and the complete unit, Hypothesis property-based, and integration test strategy.

The PDF/document-compliance work described by requirements 1.1–2.5 and 3.1–3.6 is outside this plan. No watermark, disclaimer, PDF export/generation, or `Last updated` work is included.

## Dependencies and working rules

- Tasks 1 and 2 are standalone baseline tests and must be completed before implementation tasks. Property 1 is expected to fail on the unfixed upload flow. Property 2 must pass for non-upload/direct-pipeline behavior on the unfixed flow.
- Task 3 is the first implementation task and must be complete before tasks 4–6. Tasks 4 and 5 are sequential because the runner depends on the source/progress and persistence seams.
- Task 6 follows the exact fourth implementation phase: migrate callers first, then add the remaining unit, Hypothesis, and integration coverage against the completed seams and API.
- Existing `IngestionPipeline.process_pdf(Path)` remains available throughout the work and is never replaced by a job ID.
- Upload callers are different from direct parser, pipeline, staging, and helper callers. Every upload caller and upload test must submit, poll until a terminal state, surface progress, and surface diagnostics.
- Use isolated temporary stores and injected fakes for tests. Do not require Ollama, Chroma, Streamlit, or a persistent repository data directory for unit/property tests.

## Tasks

- [ ] 1. Write the bug-condition exploration test before the fix
  - **Property 1: Bug Condition** - Accepted PDF ingestion is synchronous or unobservable
  - **CRITICAL**: Write and run this property against the UNFIXED implementation before changing application source files.
  - **GOAL**: Surface counterexamples for every part of `isBugCondition(input)` that the current upload path can demonstrate: synchronous waiting, missing status resource, absent durable progress, and opaque failure.
  - Build a controlled upload-caller test around `components.surgeons_table.render_surgeons_table()` or its current injectable seam. Use a pipeline double whose `process_pdf()` blocks on an event and a second double that raises after a chunk boundary.
  - Assert that the unfixed caller waits inside synchronous processing, exposes no `job_id`/status URL, cannot observe intermediate stage/counters, and reaches only the generic failure path after the exception.
  - Exercise non-empty bytes with a `.pdf` name but no `%PDF-` header through the current upload helper. Record that extension/non-empty validation accepts the bytes and parse failure is deferred to synchronous processing.
  - Exercise a slow triple-extraction double and a failure after vector/staging work. Record that no externally pollable progress or job-scoped replay/status contract exists.
  - For deterministic current behavior, scope generated cases to bounded filenames, non-empty byte payloads, and a blocking/failing pipeline double rather than using real sleeps or a real model service.
  - **EXPECTED OUTCOME ON UNFIXED CODE**: The test fails because the callback blocks or returns only final synchronous behavior, no status resource is available, and diagnostics are not represented by a durable job status.
  - Document at least one concrete counterexample, such as a non-empty `report.pdf` payload lacking `%PDF-` that reaches parsing, or a blocked `process_pdf()` call with no status URL.
  - _Bug_Condition: `accepted AND (synchronous_wait OR missing_status OR unpolled_job OR opaque_failure)` from the design.
  - _Expected_Behavior: Return a job ID/status URL promptly, then expose monotonic progress through a terminal result or structured diagnostic.
  - _Requirements: 2.11_

- [ ] 2. Write preservation property tests before implementation
  - **Property 2: Preservation** - Direct extraction and non-upload behavior remain compatible
  - **IMPORTANT**: Follow observation-first methodology and run these tests on the UNFIXED code before implementation.
  - Generate representative page/chunk inputs and use injected parser, entity, triple, vector, and staging doubles to observe the current direct pipeline behavior without invoking an upload caller.
  - Capture and assert the existing `PDFChunk` text, page numbers, overlap, stable IDs, evidence grounding, SHACL classification, staging categories, vector metadata, and `PipelineMetrics` semantics for non-buggy direct calls.
  - Assert that `IngestionPipeline.process_pdf(Path)` remains synchronous and returns `PipelineMetrics`; direct callers do not need to interpret a job ID.
  - Cover parser page-warning continuation, fatal unreadable-PDF behavior, no-triple chunks, valid/quarantined staging, and the fact that approved graph publication remains a separate explicit action.
  - Verify the current direct path keeps default `chunk_size=1000` and `chunk_overlap=200` and does not perform PDF generation, export, watermarking, disclaimer insertion, or date validation.
  - **EXPECTED OUTCOME ON UNFIXED CODE**: These non-upload preservation tests pass. If a test reveals an existing unrelated failure, record it as a baseline and do not weaken the post-fix target.
  - _Preservation: Existing extraction, persistence, staging, and synchronous compatibility behavior from the design must remain unchanged outside the asynchronous upload boundary._
  - _Requirements: 2.11_

- [ ] 3. Implement core job contracts and storage
  - **Dependency**: Complete tasks 1 and 2, including documenting the exploration counterexample and preservation baseline.
  - **Implementation order**: Make only the first source phase in this task before moving to pipeline seams.

  - [ ] 3.1 Add `src/ingestor/job_models.py` API and persistence contracts
    - Define Pydantic models for `JobSubmissionResponse`, `JobProgress`, `JobDiagnostic`, `JobResult`, `IngestionJobStatus`, source metadata, configuration, lifecycle status, and stage enums.
    - Model statuses as `queued`, `running`, `completed`, `partial`, `failed`, and `canceled`; identify the terminal statuses explicitly.
    - Validate `progress.fraction` in `[0, 1]`, use default factories for collections, require timezone-aware timestamps, and enforce monotonic non-negative counters at update boundaries.
    - Keep public diagnostics safe: expose stable code, stage, message, retryability, and optional chunk ID/details, but never exception traces, absolute paths, prompts, uploaded content, secrets, or local filesystem locations.
    - Serialize terminal results with `total_chunks`, `processed_chunks`, `failed_chunks`, `total_triples`, `valid_triples`, `quarantined_triples`, `vector_insertions`, `duration_seconds`, and persisted document/staging identifiers.
    - **Acceptance criteria**: Valid queued/running/terminal examples round-trip through the models; invalid status/stage, fraction, timestamp, and negative-count inputs fail validation; diagnostic serialization contains no forbidden sensitive fields.
    - _Design references: Expected Behavior—Upload and status API schemas; Expected Behavior—Job lifecycle; Fix Implementation—API contracts._
    - _Requirements: 2.11_

  - [ ] 3.2 Add `src/ingestor/upload_store.py` bounded upload spooling
    - Implement `UploadedPdfStore` to copy multipart input in bounded blocks without calling `getvalue()` for the complete upload.
    - Enforce safe generated filenames, non-empty input, maximum byte size, disk-space/error handling, and the initial `%PDF-` signature check.
    - Compute SHA-256 while copying and atomically rename a temporary file into `data/uploads/jobs/{job_id}/source.pdf` or the configured job directory.
    - Return a seekable path/handle suitable for `pypdf`, retain the source through retry/recovery, and avoid returning local paths in public models.
    - Provide deterministic cleanup behavior for failed pre-queue validation and preserve the source for accepted jobs.
    - **Acceptance criteria**: bounded reads are observable with a chunked fake stream; valid input gets a stable hash and atomically committed source; empty, oversized, non-PDF, unsafe-name, and I/O failures map to documented validation errors; rejected uploads never enqueue work.
    - _Design references: Fix Implementation—`UploadedPdfStore`; Error and retry policy; Incremental chunking and progress calculation._
    - _Requirements: 2.11_

  - [ ] 3.3 Add `src/ingestor/job_store.py` durable manifests and recovery
    - Implement `IngestionJobStore` with one JSON manifest per job under the configured job directory and an append-only diagnostic/event log.
    - Write status snapshots through a temporary file and atomic replace, protected by a file lock or process-local lock, so readers never see partial JSON.
    - Validate lifecycle transitions, use compare-and-set semantics to claim queued jobs, and reject updates to terminal fields except an allowed recovery note.
    - Persist source metadata, configuration, counters, stage, timestamps, diagnostics, result metrics, checkpoint location, and completed chunk IDs.
    - On startup, detect stale `running` jobs and mark them `failed` with `JOB_WORKER_INTERRUPTED`, or make them recoverable when source and checkpoint state are intact according to the selected policy.
    - **Acceptance criteria**: Concurrent update tests see complete JSON snapshots; illegal transitions and double claims fail safely; counters never decrease; terminal records remain immutable; unknown job lookup is distinguishable from storage failure; stale-worker recovery is deterministic and preserves completed chunk IDs.
    - _Design references: Fix Implementation—`IngestionJobStore`; Job lifecycle; Correctness Property 3: Incremental persistence and replay safety._
    - _Requirements: 2.11_

  - [ ] 3.4 Verify the core contracts independently
    - Run focused tests for model validation, bounded spooling, atomic status writes, compare-and-set claims, monotonic updates, terminal immutability, and startup orphan recovery before adding runner code.
    - Confirm no application files outside `src/ingestor/job_models.py`, `src/ingestor/upload_store.py`, and `src/ingestor/job_store.py` are changed in this phase.
    - **Acceptance criteria**: Focused core-contract tests pass; a process interruption cannot leave a partially written `status.json`; recovered jobs contain a safe diagnostic and a usable source/checkpoint decision.
    - _Design references: Correctness Properties 1 and 3; Testing Strategy—Job models/store and upload spooling.
    - _Requirements: 2.11_

- [ ] 4. Implement pipeline seams and incremental persistence
  - **Dependency**: Task 3 must pass its focused contract tests. Keep the exact source order in this task: persistence coordinator, parser seams, then pipeline core.

  - [ ] 4.1 Add `src/ingestor/incremental_persistence.py`
    - Implement `IncrementalPersistenceCoordinator` with a serialized per-job persistence boundary.
    - Upsert vector text using stable `PDFChunk.id`, document/page/chunk/source metadata, and job/source identifiers. Preserve the fallback for injected vector stores that do not accept `ids`.
    - Generate deterministic staging idempotency keys from source hash, chunk ID, triple index/content fingerprint, and extraction configuration. Record keys in the job manifest or durable ledger before replay can duplicate a write, while preserving existing staging manager semantics.
    - Write the completed-chunk checkpoint only after required vector and staging writes succeed. Record per-step failures and never mark an incomplete chunk as completed.
    - Keep approved graph publication out of ingestion; reviewer actions still call explicit approval methods.
    - **Acceptance criteria**: Replaying a completed chunk produces no duplicate stable vector or staging entries; failures at vector, staging, and checkpoint steps leave a diagnostic and resumable state; valid/quarantined candidates retain existing categories; approved graph contents remain unchanged.
    - _Bug_Condition: A process interruption after persistence has no job-scoped idempotent replay contract._
    - _Expected_Behavior: Completed writes survive replay without duplicates and the next run resumes from a matching source/configuration checkpoint._
    - _Preservation: Keep vector metadata, stable chunk IDs, staging semantics, and separate HITL approval unchanged._
    - _Design references: Correctness Property 3; Fix Implementation—`IncrementalPersistenceCoordinator`; Error and retry policy.
    - _Requirements: 2.11_

  - [ ] 4.2 Extend `src/ingestor/pdf_parser.py` with seekable byte-stream and progress hooks
    - Preserve `parse_pdf(Path)` and `parse_pdf_streaming(Path)` signatures and existing chunk text, IDs, overlap, and page-warning behavior.
    - Add a source abstraction or helper that accepts a seekable binary stream plus `document_name` and optional source hash, while retaining path support for direct callers.
    - Report `pages_processed`, `pages_total`, and chunks discovered through an optional progress/event sink after each page/chunk without changing parser extraction semantics.
    - Spool before opening `PdfReader`; do not claim that a non-seekable socket can be passed directly to `pypdf`.
    - Keep PDF generation/export and all watermark/disclaimer/date concerns out of this module.
    - **Acceptance criteria**: The same fixture PDF parsed from a path and seekable `BytesIO`/spooled source yields identical chunk text, page numbers, overlap, IDs, and warnings; malformed bytes produce a safe parse diagnostic; progress callbacks are ordered and do not materialize all chunks.
    - _Design references: Fix Implementation—`PDFParser`; Incremental chunking and progress calculation; Preservation requirements.
    - _Requirements: 2.11_

  - [ ] 4.3 Refactor `src/ingestor/pipeline.py` around an internal async-friendly core
    - Extract the current `process_pdf()` body into a source-oriented internal method accepting parser source, job context, progress sink, checkpoint, and persistence coordinator.
    - Keep `process_pdf(Path)` intact as a synchronous compatibility wrapper returning `PipelineMetrics` with existing direct error/status behavior.
    - Use job-scoped checkpoint paths for job execution while allowing the compatibility wrapper to retain its configured behavior.
    - Publish progress/metrics after each page/chunk and persistence step, including diagnostics, without changing entity extraction, evidence grounding, SHACL classification, triple fallback, vector metadata, or staging behavior.
    - Preserve existing bounded entity preprocessing and sequential LLM behavior at this seam; async runner threading and semaphores belong to task 5.
    - **Acceptance criteria**: Existing direct pipeline tests pass unchanged or with only seam-injection updates; direct callers receive `PipelineMetrics`; job-core calls can emit progress and resume from a checkpoint; a no-triple chunk still counts and persists as before; approved graph publication is not introduced.
    - _Bug_Condition: The synchronous implementation has no reusable progress/checkpoint seam for a durable job boundary._
    - _Expected_Behavior: The runner can invoke the internal core incrementally while `process_pdf(Path)` preserves synchronous compatibility._
    - _Preservation: Existing extraction and direct caller semantics remain unchanged._
    - _Design references: Fix Implementation—`IngestionPipeline`; Preservation requirements; Correctness Property 2.
    - _Requirements: 2.11_

  - [ ] 4.4 Verify pipeline and replay behavior before API work
    - Re-run the same Property 2 preservation tests from task 2 against the refactored core and compatibility wrapper.
    - Add focused checks that a failure after each persistence step resumes without duplicate writes and that parser progress counters are monotonic.
    - **Acceptance criteria**: Property 2 still passes; direct `process_pdf(Path)` behavior is preserved; replay tests pass; no API route or Streamlit caller is required to understand the internal core yet.
    - _Design references: Testing Strategy—Preservation checking, Incremental persistence, Compatibility wrapper.
    - _Requirements: 2.11_

- [ ] 5. Implement the async runner and FastAPI routes
  - **Dependency**: Complete task 4 and verify the internal core, progress sink, and persistence coordinator before wiring the runner.
  - **Implementation order**: Implement runner ownership/concurrency first, then routes and lifespan management.

  - [ ] 5.1 Add `src/ingestor/job_runner.py` bounded asynchronous execution
    - Implement `AsyncIngestionJobRunner` with an `asyncio.Queue(maxsize=N)`, configured active-job semaphore, explicit task ownership, and clean startup/shutdown.
    - Claim jobs from `IngestionJobStore`, run blocking parser/entity/Ollama/Chroma/staging methods through `asyncio.to_thread()` or a bounded executor, and emit status after validation, parser progress, each chunk, each diagnostic, persistence, and finalization.
    - Apply separate job, chunk, entity, LLM, and persistence limits. Keep LLM concurrency at one by default and preserve existing bounded entity preprocessing.
    - Enforce stage/chunk deadlines with `asyncio.wait_for()` while retaining existing HTTP retry/timeouts. Prevent timed-out or canceled late thread results from committing through job-generation/checkpoint guards.
    - Map outcomes to `completed`, `partial`, `failed`, or `canceled` according to the design. Preserve useful completed chunks and safe diagnostics.
    - **Acceptance criteria**: Submission returns before extraction completes; queued-to-terminal transitions are persisted; active counts never exceed configured limits; slow work does not block unrelated status reads; late results cannot mutate a newer generation or completed job; shutdown does not abandon owned tasks without a status update.
    - _Bug_Condition: Accepted work blocks the caller and has no durable observable lifecycle._
    - _Expected_Behavior: Every accepted job is claimed and progresses to a terminal state with monotonic counters and structured diagnostics._
    - _Design references: Correctness Property 1: Uploaded ingestion becomes observable and non-blocking; Correctness Property 4: Bounded asynchronous execution; Bounded asyncio concurrency; Error and retry policy.
    - _Requirements: 2.11_

  - [ ] 5.2 Add `POST /ingestion/jobs` and `GET /ingestion/jobs/{job_id}` in `src/api/main.py`
    - Add multipart upload submission that uses `UploadedPdfStore`, creates the durable queued manifest, enqueues the job, and returns HTTP `202` with `job_id`, `status`, `status_url`, source metadata, and creation time. Do not return final extraction metrics from submission.
    - Add status lookup returning the modeled job status. Return `404` for unknown jobs and `503` only when the runner cannot accept work.
    - Map invalid form/configuration to `400`, upload size limits to `413`, and non-PDF content to `415`. Processing errors after acceptance remain in the status resource instead of becoming a later HTTP 500 from the original request.
    - Redact source paths and sensitive diagnostics from all public responses.
    - **Acceptance criteria**: A valid upload immediately returns `202` and a pollable URL; malformed/empty/oversized uploads receive documented pre-queue responses and create no worker; status responses validate against `IngestionJobStatus`; accepted parse/extraction failures remain observable through terminal status.
    - _Design references: Expected Behavior—Upload and status API schemas; Job lifecycle; Fix Implementation—FastAPI routes; Error and retry policy.
    - _Requirements: 2.11_

  - [ ] 5.3 Manage runner startup and shutdown through application lifespan
    - Initialize the upload store, job store, runner, and configured dependencies in the FastAPI lifespan rather than creating request-local background tasks.
    - Run stale-worker/orphan recovery at startup, start the runner before accepting submissions, and stop/drain owned tasks cleanly at shutdown.
    - Keep existing query and health routes working and avoid changing unrelated API behavior.
    - **Acceptance criteria**: ASGI lifespan tests show the runner is available during requests, stale jobs are recovered on startup, shutdown persists safe terminal/recovery state, and repeated app startup does not create duplicate worker owners.
    - _Design references: Fix Implementation—`IngestionJobStore`, `AsyncIngestionJobRunner`, and API lifespan; Testing Strategy—Restart/recovery.
    - _Requirements: 2.11_

  - [ ] 5.4 Verify the API contract and expected behavior property
    - Re-run the same exploration scenario from task 1 through the new API seam, without writing a replacement property.
    - Assert immediate `202`, present `job_id`, valid status URL, monotonic progress/counters, valid stages, terminal status, and safe diagnostics for failure/partial cases.
    - **Property 1: Expected Behavior** - Accepted PDF jobs are observable through terminal completion or failure
    - **IMPORTANT**: The original task 1 test now passes; it must prove the fix rather than be weakened or replaced.
    - **Acceptance criteria**: Property 1 passes for slow, malformed, and injected failure scenarios; accepted failures do not surface only as request exceptions; all terminal non-success states include a structured diagnostic.
    - _Design references: Correctness Property 1; Fix checking pseudocode; Error and retry policy._
    - _Requirements: 2.11_

- [ ] 6. Migrate callers and complete unit, property-based, and integration tests
  - **Dependency**: Complete task 5 and verify the API contract before migrating frontend behavior.
  - **Implementation order**: Migrate `components/surgeons_table.py` and `app.py` first, then add the remaining approved test strategy coverage.

  - [ ] 6.1 Migrate `components/surgeons_table.py` and `app.py` to an injectable submit-and-poll client
    - Replace the direct `pipeline.process_pdf()` upload callback in `render_surgeons_table()` with a client that submits the uploaded PDF, retains `job_id`, and polls `GET /ingestion/jobs/{job_id}` until `completed`, `partial`, `failed`, or `canceled`.
    - Poll immediately once, then use a bounded configurable interval, update `st.progress`/stage/counters, and retain the job ID if a client-side wait limit stops polling. A client wait limit must not mark the server job failed.
    - Render every terminal and warning diagnostic with its code/message/stage; use a generic fallback only when the status resource itself cannot be read.
    - Keep `surgeons_progress_stage`, `surgeons_pipeline`, staging-manager loading, table actions, safe filename behavior, and existing UI settings compatible. After completion, load the job’s configured staging manager rather than assuming request-local synchronous completion.
    - Provide an injectable client seam for tests so no running external server is required.
    - **Acceptance criteria**: The frontend never treats the `job_id` response as final metrics; fake clients are polled until each terminal state; progress and all diagnostics render; partial/failure/cancel states are handled distinctly; direct non-upload helper behavior remains available.
    - _Bug_Condition: A frontend upload caller receives or creates asynchronous work but does not poll until terminal state._
    - _Expected_Behavior: Every frontend upload caller polls, surfaces progress, and surfaces diagnostic errors._
    - _Preservation: Existing table rendering, staging/HITL actions, safe filename behavior, and direct pipeline compatibility remain intact._
    - _Design references: Preservation requirements—Caller migration; Polling behavior; Fix Implementation—caller migration._
    - _Requirements: 2.11_

  - [ ] 6.2 Audit and migrate every automated upload caller
    - Search all tests and application code for upload submission, `job_id`, `process_pdf()` in upload flows, `render_surgeons_table()` upload paths, and assertions that expect final metrics immediately after upload.
    - Update every upload API/frontend test to poll the status endpoint until terminal completion or failure, never sleep once and assume completion, and assert surfaced progress and diagnostic messages.
    - Keep direct parser/pipeline/staging/helper tests direct when they are not upload callers; explicitly document why they do not need polling.
    - **Acceptance criteria**: The repository audit identifies every existing upload caller; each caller uses submit-and-poll semantics; no upload test asserts triples/metrics directly from `202`; each failure/partial test asserts a visible stable diagnostic; no caller silently drops the returned job ID.
    - _Requirements: 2.11_

  - [ ] 6.3 Add unit coverage from the approved testing strategy
    - Cover upload spooling/validation: bounded block copying, safe names, SHA-256, empty/oversized/non-PDF rejection, atomic rename, and cleanup.
    - Cover byte-stream parser equivalence and parse diagnostics; job model/store validation, atomic writes, transition rules, monotonic counters, terminal immutability, 404 lookup, and stale-worker recovery.
    - Cover runner lifecycle, stage events, job-specific checkpoints, shutdown, diagnostic redaction, bounded concurrency, timeouts/retries, and late-result guards.
    - Cover incremental persistence failures after each write step, checkpoint resume, stable vector upsert, deterministic staging idempotency keys, and no duplicate replay writes.
    - Cover `process_pdf(Path)` compatibility and the injectable Streamlit caller seam, including progress/counter/diagnostic rendering for every terminal state.
    - **Acceptance criteria**: Unit tests isolate external services, exercise success and failure paths, and pass without modifying persistent repository data or requiring a real Ollama service.
    - _Design references: Testing Strategy—Unit tests; Correctness Properties 2–4._
    - _Requirements: 2.11_

  - [ ] 6.4 Add Hypothesis property-based tests from the approved strategy
    - **Property 3: Incremental Persistence and Replay Safety** - Generate bounded chunk sequences and inject failure at any chunk/stage. Assert completed chunk IDs and counters are monotonic, successful writes are retained, replay is idempotent, and terminal failure/partial status has a diagnostic.
    - **Property 4: Bounded Asynchronous Execution** - Generate valid job/chunk counts and semaphore configurations. Assert active jobs, chunks, entity tasks, LLM calls, and persistence operations never exceed configured limits; default LLM concurrency remains one.
    - Generate valid/invalid byte prefixes and filenames. Assert validation returns only documented acceptance/rejection classes and rejected input never starts a worker.
    - Generate delayed poll responses and terminal states. Assert the frontend poller continues until terminal, updates progress, retains the job ID when its local wait limit expires, and surfaces diagnostic messages.
    - Generate equivalent path and spooled-byte sources for the same fixture PDF. Assert stable chunk text, IDs, metadata, and extraction classification.
    - Use the required hover format for each property task and update the PBT task status after execution.
    - **Acceptance criteria**: Hypothesis tests pass across generated examples without fixed sleeps; any failure records the exact counterexample; generated scenarios cannot exceed configured concurrency or duplicate persistence.
    - _Design references: Correctness Properties 3 and 4; Testing Strategy—Property-based tests._
    - _Requirements: 2.11_

  - [ ] 6.5 Add integration coverage for API completion, failure, partial results, frontend migration, and restart recovery
    - Test a small real PDF through `TestClient` or ASGI transport: submit, assert `202`/`job_id`, poll repeatedly, and assert terminal `completed` metrics, vector persistence, and staged records.
    - Test corrupt or unsupported bytes: submit through the documented validation path or accepted-job path as appropriate, poll accepted jobs to `failed`, and assert a structured parse diagnostic without an original-request HTTP 500.
    - Inject one timed-out/failing chunk and poll to `partial`; assert successful chunks remain searchable/staged and the failed chunk diagnostic is present.
    - Exercise the Surgeon’s Table upload client against the ASGI app or an injected endpoint client; assert progress, terminal handling, staging-manager availability, and diagnostic rendering.
    - Stop/restart the runner after a persisted chunk; recover the job manifest and assert replay does not duplicate vectors or staging entries.
    - Run existing direct integration pipeline tests and compare metrics/status expectations with the internal core implementation.
    - **Acceptance criteria**: Every integration upload test polls until terminal; completion, partial, failure, and recovery behavior are observable and deterministic in isolated temporary stores; direct compatibility tests continue to pass.
    - _Design references: Testing Strategy—Integration tests; Fix checking; Preservation checking; Correctness Properties 1–3._
    - _Requirements: 2.11_

  - [ ] 6.6 Verify the same preservation tests after caller migration
    - **Property 2: Preservation** - Direct extraction and non-upload behavior remain compatible
    - **IMPORTANT**: Re-run the SAME tests from task 2 and task 4.4; do not replace them with asynchronous assertions.
    - Confirm direct `process_pdf(Path)`, parser, staging, vector, and HITL approval behavior remains unchanged, while upload callers now use only the asynchronous contract.
    - **EXPECTED OUTCOME**: Tests PASS, confirming no regression outside the asynchronous upload boundary.
    - _Requirements: 2.11_

- [ ] 7. Checkpoint - Run the complete validation suite
  - Run focused tests for tasks 3–6, the original task 1 exploration property after the fix, the original task 2 preservation property, all new API/polling/concurrency/persistence/recovery tests, and the existing repository test suite.
  - Prefer `python -m pytest -q` if `pytest` is not directly available, and record the exact command used.
  - Confirm every existing frontend upload caller and automated upload test submits, polls to terminal, surfaces progress, and surfaces diagnostic errors as required by 2.11.
  - Confirm no PDF generation/export, watermark, disclaimer, company-name, or `Last updated` implementation was added to this bugfix.
  - Confirm application source changes follow the exact order: core contracts/storage, pipeline seams/persistence, runner/routes, then caller migration/tests.
  - **Acceptance criteria**: All tests pass; direct compatibility and HITL approval remain intact; accepted jobs reach a terminal state; rejected uploads do not start workers; no duplicate replay writes occur; no unresolved traceability or scope-boundary issue remains.
  - _Design references: Scope boundary; Testing Strategy—Validation approach; Correctness Properties 1–4._
  - _Requirements: 2.11_

## Traceability and scope notes

- **Requirement 2.11** is the sole requirement in this plan. It is addressed by the durable job contract, immediate `202` submission, status polling, progress/diagnostic models, bounded runner, frontend migration, upload-test migration, and terminal-state integration tests.
- **Bug condition `C(X)`** is explored in task 1 and fixed/verified in task 5.4 and task 6.1–6.2.
- **Preservation `¬C(X)`** is observed in task 2 and rechecked in tasks 4.4 and 6.6. The synchronous `process_pdf(Path)` wrapper and extraction semantics remain supported.
- **Correctness Property 1** is covered by tasks 1 and 5.4.
- **Correctness Property 2** is covered by tasks 2, 4.4, and 6.6.
- **Correctness Property 3** is covered by tasks 4.1, 6.3–6.5.
- **Correctness Property 4** is covered by tasks 5.1, 6.3, and 6.4.
- The separate PDF/document-compliance scope remains untouched: no task changes PDF generation or export, document rendering, watermarking, company disclaimers, company-name handling, or `Last updated` metadata.

## Notes

- Tasks 1 and 2 are intentionally standalone pre-fix tests required by the bug-condition workflow. Property 1 is expected to fail before implementation and pass after the API/runner fix; Property 2 must establish the direct-call baseline before implementation.
- The four implementation phases remain in the requested order inside tasks 3–6: core contracts/storage, pipeline seams/incremental persistence, async runner/routes, then caller migration and the remaining test strategy.
- Hypothesis tasks use the required `**Property N: Type** - [Title]` format. PBT execution must record the exact failing example when a generated case fails.
- No application source files are modified by creation of this task artifact. The task list itself is the only generated file in this workflow step.
