# Implementation Plan

## Scope

Implement the Ollama timeout, asynchronous baseline startup, and local virtual-environment activation fixes described in `bugfix.md` and `design.md`.

Production changes are limited to:

- `src/ingestor/triple_extractor.py`
- `src/api/main.py`
- `start.sh`

Test changes are limited to the focused existing test modules and a new focused module only when needed. Do not change retrieval algorithms, ingestion algorithms, baseline-loader idempotency, or unrelated deployment behavior.

## Execution Rules

- Complete tasks in order.
- Tasks 1 and 2 are observation-first tests. Run them against the unfixed implementation before changing production code.
- Do not change production code while completing tasks 1 or 2.
- Task 3 implements the fix and must reuse the tests from tasks 1 and 2.
- Task 4 is the final validation checkpoint.
- Keep every task status as `[ ]` until the task is actually completed. Do not manually mark a task `[in_progress]`; the task runner owns that state.

## Tasks

- [x] 1. Capture bug-condition behavior before implementing the fix
  - **Property 1: Bug condition** - The current implementation uses an insufficient Ollama timeout, blocks API readiness on baseline preload, and skips an existing local virtual-environment activation file.
  - Add focused tests in `tests/unit/test_task18_resilience.py`, a new `tests/unit/test_ollama_timeout_startup.py`, and `tests/test_start_script.py` as appropriate.
  - Run the tests against the unfixed implementation. The expected result is that the new bug-condition tests fail for the known defects.
  - For extraction, construct `TripleExtractor()` without an explicit timeout, fake `extractor.session.post`, record the request timeout, and model a valid response that completes after 30 seconds but within the supported longer window. Capture the current `30.0` timeout and retry behavior.
  - For API startup, patch or fake `bootstrap_baseline_corpus` so it remains pending, enter `src.api.main.lifespan`, and demonstrate that the unfixed lifespan cannot reach its yielded section until preload completes.
  - For `start.sh`, create an isolated temporary application directory with `venv/bin/activate`, fake `curl`, `ollama`, `uvicorn`, and `streamlit` commands, and verify that the unfixed launcher does not expose the activation marker.
  - Keep these tests deterministic and local. Do not require a live Ollama service, network access, or full baseline ingestion.
  - Record the observed counterexamples in test names, assertions, or focused test documentation.
  - Requirements: 1.1, 1.2, 1.4, 1.5

- [x] 2. Record preservation behavior before implementing the fix
  - **Property 2: Preservation** - Existing behavior remains unchanged for inputs outside the bug condition.
  - Run these tests against the unfixed implementation and confirm they pass before task 3 changes production code.
  - Preserve explicit `TripleExtractorConfig.timeout_seconds`, including explicit values when `OLLAMA_TIMEOUT` is set. Preserve the existing Pydantic bounds and validation behavior for explicit values.
  - Preserve genuine transient Ollama failure behavior. Cover failure counts within `max_retries`, attempt counts, exponential backoff, `TripleExtractorError`, fallback behavior, and `last_error` reporting.
  - Retain regression coverage for response parsing, evidence validation, ontology canonicalization, confidence filtering, and triple limiting.
  - Cover `BASELINE_INGEST_ON_STARTUP=0`, `false`, and `no`. Assert that no preload is scheduled and that retriever, stores, runner, health, and shutdown behavior remain available.
  - Cover enabled baseline startup with an already-completed loader, a loader exception, and shutdown cancellation. Preserve completion logging, failure logging without API teardown, and cleanup of the managed task.
  - Preserve `start.sh` behavior when no activation file exists, including runtime directories, Ollama readiness polling, model pull and cache behavior, FastAPI health polling, environment overrides, signal handling, Streamlit launch, and child-process cleanup.
  - Extend existing launcher tests only for missing activation coverage when that assertion is absent.
  - Tests belong in `tests/unit/test_task18_resilience.py`, `tests/unit/test_ingestor.py`, `tests/unit/test_ollama_timeout_startup.py` when present, and `tests/test_start_script.py` as appropriate.
  - Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7

- [ ] 3. Implement the production fixes without unrelated refactoring
  - Reuse the bug-condition and preservation tests from tasks 1 and 2. Do not replace them with weaker tests.
  - **3.1 Update Ollama timeout resolution in `src/ingestor/triple_extractor.py`**
    - Change the default `TripleExtractorConfig.timeout_seconds` from `30.0` to `120.0`.
    - Retain the supported bounds of `5.0` through `120.0`.
    - Read `OLLAMA_TIMEOUT` only when the caller omits `timeout_seconds`.
    - Parse a trimmed finite decimal value. Accept only values inside the supported bounds.
    - Fall back to `120.0` when the variable is unset, blank, malformed, non-finite, or out of range. Log a warning for invalid non-blank values.
    - Preserve explicit configuration precedence and existing Pydantic validation for explicit values.
    - Continue passing `self.config.timeout_seconds` to `Session.post(timeout=...)`.
    - Do not change retry count, backoff, parsing, error, fallback, or evidence-validation behavior.
    - Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3
  - **3.2 Make baseline preload lifecycle-managed in `src/api/main.py`**
    - Add a local `baseline_task = None` owner in `lifespan`.
    - Preserve disabled values `0`, `false`, and `no`; these values must schedule no preload task.
    - When enabled, schedule one task that awaits `asyncio.to_thread(bootstrap_baseline_corpus)` before the existing store and runner setup, but do not await it before `yield`.
    - Log successful completion and the returned action mapping.
    - Log ordinary preload exceptions with traceback without tearing down the API lifecycle.
    - Re-raise `asyncio.CancelledError` so shutdown can handle cancellation.
    - Preserve the existing retriever, stores, pipeline factory, job-runner initialization, health, and cleanup behavior.
    - During shutdown, cancel a pending task, await it under cancellation suppression, and retrieve completed task outcomes so no exception is unobserved. Do not attempt to force-stop the worker thread.
    - Requirements: 2.4, 2.5, 2.6, 3.4, 3.5, 3.6
  - **3.3 Source the local virtual environment conditionally in `start.sh`**
    - After `APP_DIR` is resolved and `log()` is available, but before `require_commands`, source `${APP_DIR}/venv/bin/activate` when it exists.
    - Log successful activation.
    - Treat a missing activation file as a normal branch and continue the existing startup flow.
    - Ensure activation occurs before command resolution and Python-based service startup.
    - Leave Ollama readiness, model pull and cache behavior, FastAPI health polling, environment overrides, signal handling, and cleanup unchanged.
    - Requirements: 2.7, 3.7

- [ ] 4. Verify the fix and run the complete test suite
  - Re-run the exact bug-condition tests from task 1. They must now pass.
  - Re-run the exact preservation tests from task 2. They must still pass.
  - Run the focused extractor, API lifespan, and launcher tests first.
  - Run the complete repository suite exactly as `pytest -q` from `/Users/froilansia/git/alchemists-chimera`.
  - Confirm the suite does not require a live Ollama model, network service, or full baseline ingestion dependency.
  - Confirm only the scoped production files and focused test files changed.
  - Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7

## Completion Criteria

- The task runner recognizes every top-level task and subtask.
- Tasks 1 and 2 pass against the unfixed implementation before task 3 begins, with task 1 documenting the expected defect failures.
- The implementation satisfies the bug-condition tests without changing preserved behavior.
- The focused tests and `pytest -q` pass after task 3.
