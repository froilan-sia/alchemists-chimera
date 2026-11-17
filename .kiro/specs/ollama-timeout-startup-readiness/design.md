# Ollama Timeout and Startup Readiness Bugfix Design

## Overview

This bugfix addresses three related startup and ingestion problems in the local RAG service. Ollama triple extraction currently uses a 30-second request timeout, which is too short for cold or CPU-bound `qwen2.5:3b` generation and causes the existing retry loop to repeat requests that only timed out. FastAPI startup also waits synchronously, through a worker thread, for the baseline corpus to finish loading before the lifespan yields, so the API health endpoint cannot become available during that work. Finally, `start.sh` does not source a repository-local virtual environment before resolving Python-based commands.

The fix is intentionally limited to the existing configuration and request path in `src/ingestor/triple_extractor.py`, the lifespan in `src/api/main.py`, and the startup entrypoint in `start.sh`. It will raise the default Ollama timeout to 120 seconds, allow a validated `OLLAMA_TIMEOUT` override without overriding an explicit `TripleExtractorConfig.timeout_seconds`, schedule baseline loading as a managed asyncio background task, and conditionally source `${APP_DIR}/venv/bin/activate`. Existing retry, parsing, health, launcher, and shutdown behavior outside these conditions remains unchanged.

## Glossary

- **Bug_Condition (C)**: An Ollama extraction request reaches the fixed 30-second timeout, or FastAPI startup awaits baseline loading before yielding, or the launcher starts without activating an existing repository virtual environment.
- **Property (P)**: A cold/CPU-bound inference that finishes within the effective timeout succeeds without a retry; API lifespan readiness is independent of baseline completion; and an existing local virtual environment is sourced before Python-based services start.
- **Preservation**: Existing explicit extractor configuration, transient-error retry behavior, response parsing, disabled-baseline behavior, launcher readiness/model-pull/signal handling, and API component initialization remain unchanged.
- **Effective Ollama timeout**: The explicit `TripleExtractorConfig.timeout_seconds` when supplied; otherwise the valid `OLLAMA_TIMEOUT` value; otherwise the 120.0-second default.
- **Baseline preload**: The synchronous `bootstrap_baseline_corpus` operation that scans and ingests the configured files from `data/input/`.
- **Managed baseline task**: The asyncio task created by the FastAPI lifespan to await the synchronous preload through `asyncio.to_thread`, with logging, cancellation, and shutdown cleanup owned by the lifespan.
- **Launcher application directory**: The resolved `APP_DIR` value already used by `start.sh` for runtime directories and application paths.

## Bug Details

### Bug Condition

The extraction defect occurs when a valid Ollama generation request takes longer than 30 seconds, which is common while `qwen2.5:3b` loads or runs on CPU. The request then enters the existing retry loop and can produce four total attempts. The configuration also has no environment-controlled path for `OLLAMA_TIMEOUT`. Independently, the API lifespan awaits baseline corpus loading before yielding, and the launcher ignores an existing `${APP_DIR}/venv/bin/activate` file.

**Formal Specification:**

```text
FUNCTION isBugCondition(input)
  INPUT: input of type ExtractionOrStartupInput
  OUTPUT: boolean

  extraction_bug := input.kind == "ollama_request"
                    AND input.effective_timeout == 30.0
                    AND input.request_duration > 30.0
                    AND input.request_would_complete_within_supported_timeout

  readiness_bug := input.kind == "api_startup"
                   AND input.baseline_ingestion_enabled
                   AND input.baseline_preload_is_incomplete
                   AND NOT input.lifespan_has_yielded

  launcher_bug := input.kind == "launcher_start"
                  AND input.venv_activation_file_exists
                  AND NOT input.venv_activation_was_sourced

  RETURN extraction_bug OR readiness_bug OR launcher_bug
END FUNCTION
```

For extraction, the request timeout is passed to `requests.Session.post` and therefore controls the read timeout observed in the logs. The `request_would_complete_within_supported_timeout` condition distinguishes this bug from a genuinely unavailable or permanently failing Ollama service, for which the existing retry and error handling still apply.

### Examples

- **Cold extraction**: A first `qwen2.5:3b` generation takes 42 seconds and would return valid JSON. The current 30-second timeout raises a read timeout and retries the same extraction. The fixed path uses 120 seconds by default and returns the first successful response without retrying it.
- **Environment override**: With `OLLAMA_TIMEOUT=75.5` set before constructing a `TripleExtractorConfig`, the request uses `timeout=75.5` rather than 120.0 seconds. With `OLLAMA_TIMEOUT=fast`, the configuration logs a warning and falls back to the supported 120.0-second default instead of failing application startup.
- **Explicit configuration precedence**: With `OLLAMA_TIMEOUT=90` and `TripleExtractorConfig(timeout_seconds=15)`, the request still uses 15 seconds. The environment value supplies only the omitted default.
- **Baseline readiness**: When `BASELINE_INGEST_ON_STARTUP=true` and baseline loading takes several minutes, the lifespan schedules the loader, initializes the existing API services, yields, and permits `GET /health` while loading continues. A later loader failure is logged and does not terminate the API process.
- **Disabled baseline**: With `BASELINE_INGEST_ON_STARTUP=no`, no preload task is created and startup follows the existing no-baseline path.
- **Virtual environment**: If `${APP_DIR}/venv/bin/activate` exists, `start.sh` sources it before `command -v uvicorn` and before launching FastAPI or Streamlit. If it is absent, the script continues with the current command-resolution behavior.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- An explicit `TripleExtractorConfig.timeout_seconds` continues to be honored, even when `OLLAMA_TIMEOUT` is present.
- Ollama requests that fail for genuine transient reasons continue to use the existing `max_retries`, exponential backoff, `TripleExtractorError`, fallback-triple, and `last_error` behavior.
- Successful Ollama responses continue through the existing JSON cleanup, evidence validation, ontology canonicalization, confidence filtering, and triple limiting logic.
- Setting `BASELINE_INGEST_ON_STARTUP` to `0`, `false`, or `no` continues to skip baseline loading.
- The retriever, ingestion stores, job runner, health endpoint, and response-generation components continue to initialize through the same lifespan path. Asynchronous baseline loading must not make those components unavailable solely because ingestion is still running.
- Baseline preload completion and failure remain observable through logs. Shutdown must not leave the asyncio preload task owned by the lifespan running after the lifespan exits.
- `start.sh` continues to prepare runtime directories, preserve environment-variable overrides, wait for Ollama and FastAPI readiness, pull a missing model, start Streamlit, handle signals, and clean up child processes. The only launcher addition is conditional virtual-environment activation.
- When the activation file is absent, the launcher continues without failing solely because no virtual environment exists.

**Scope:**

Inputs that do not satisfy the bug condition must remain unaffected. This includes explicit extractor settings, non-timeout Ollama failures, non-baseline API startup behavior, disabled baseline startup, already-completed or missing baseline files, launcher runs without a local virtual environment, and all existing command, polling, signal, and cleanup paths.

## Hypothesized Root Cause

1. **Fixed extractor timeout**: `TripleExtractorConfig.timeout_seconds` is hard-coded to 30.0 seconds, and `_call_ollama_with_retry` passes that value directly to `requests.Session.post`. There is no environment lookup or parsing step for `OLLAMA_TIMEOUT`.

2. **Timeout too narrow for the selected model**: The current Pydantic bound and default were designed around short requests, but cold model loading and CPU generation can legitimately exceed 30 seconds. The retry loop treats the read timeout as a transient request failure, so one slow generation becomes multiple attempts.

3. **Lifespan awaits the synchronous bootstrap**: `lifespan` currently calls `await asyncio.to_thread(bootstrap_baseline_corpus)` before creating the ingestion stores and job runner and before yielding. The thread prevents the event loop from being blocked, but the ASGI application is still not ready because the lifespan has not yielded.

4. **No lifecycle owner for background preload**: Moving the call to `asyncio.create_task` without retaining and cancelling the task would allow exceptions to become unobserved and could leave work running after shutdown. The lifespan needs a task reference, an exception-logging wrapper, and cancellation/await cleanup in its `finally` block.

5. **Launcher assumes globally resolved tools**: `start.sh` computes `APP_DIR` but never checks for or sources `${APP_DIR}/venv/bin/activate`. As a result, `uvicorn` and other Python commands may be absent from `PATH` even when the repository virtual environment is present.

## Correctness Properties

Property 1: Bug Condition - Ollama Requests and Startup Become Ready Within the Intended Lifecycle

_For any_ input where the bug condition holds (isBugCondition returns true), the fixed implementation SHALL use 120.0 seconds when no override is supplied, use a valid supported `OLLAMA_TIMEOUT` value when supplied, allow an inference that completes within the effective timeout to succeed on its first successful attempt, yield the FastAPI lifespan without awaiting baseline preload completion, log background preload completion or failure while keeping the API available, cancel and await the preload task during shutdown, and source an existing `${APP_DIR}/venv/bin/activate` before starting Python-based services.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.7**

Property 2: Preservation - Existing Extraction, API, and Launcher Behavior

_For any_ input where the bug condition does NOT hold (isBugCondition returns false), the fixed implementation SHALL produce the same result as the original implementation, preserving explicit timeout configuration, bounded transient-error retries and backoff, successful response parsing, disabled-baseline startup, API component availability, shutdown error handling, launcher readiness/model-pull/override/signal/cleanup behavior, and the full existing test-suite contract.

**Validates: Requirements 2.6, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct:

**File**: `src/ingestor/triple_extractor.py` (current configuration near lines 43-95; request call near lines 504-557)

**Function/Class**: `TripleExtractorConfig` and `_call_ollama_with_retry`

1. **Raise the default timeout**: Change the `timeout_seconds` default from `30.0` to `120.0`, retaining the existing supported range of 5.0 through 120.0 seconds unless tests or project policy require a narrower validation rule.

2. **Resolve `OLLAMA_TIMEOUT` only for omitted values**: Add a small configuration-level resolver or Pydantic `default_factory` that reads `OLLAMA_TIMEOUT` when a caller does not supply `timeout_seconds`. Parse a trimmed decimal string as a finite float, accept only values within the supported field bounds, and return 120.0 when the variable is unset, blank, malformed, non-finite, or outside those bounds. Log a warning for an invalid non-blank environment value. A default factory is preferred because it is evaluated when each configuration is constructed and therefore respects values set before application startup.

3. **Preserve explicit precedence**: Do not overwrite a caller-provided `timeout_seconds`. Pydantic field validation must still reject or otherwise handle explicitly supplied values according to the existing model contract; the environment resolver must not replace explicit configuration with an environment value.

4. **Use the effective value at the existing request boundary**: Keep `_call_ollama_with_retry` request and retry structure unchanged, but continue passing `self.config.timeout_seconds` to `Session.post(timeout=...)`. This makes the new default and environment value effective without changing retry count, backoff, response parsing, or failure reporting.

**File**: `src/api/main.py` (current lifespan near lines 91-139)

**Function**: `lifespan`

5. **Add a managed task reference**: Introduce a local `baseline_task` initialized to `None`. When baseline ingestion is enabled, import the existing `bootstrap_baseline_corpus` function and create one task that awaits `asyncio.to_thread(bootstrap_baseline_corpus)`. Retain the task reference in the lifespan so it can be observed and cleaned up.

6. **Separate preload completion from readiness**: Schedule the background task before the existing store/job-runner setup, but do not await it before the lifespan `yield`. Keep the existing retriever, stores, pipeline factory, and `job_runner.start()` initialization in the same order unless a test demonstrates a dependency that requires a minimal ordering adjustment. Once those initialization steps complete, yield while the preload task may still be pending.

7. **Handle task outcomes explicitly**: Wrap the background preload coroutine so successful completion logs the returned action mapping, ordinary exceptions log a warning with traceback and do not escape into the API lifecycle, and `asyncio.CancelledError` is re-raised so shutdown cancellation remains distinguishable from a failed preload.

8. **Cancel and await at shutdown**: In the lifespan `finally` block, cancel the baseline task if it is still pending and await it under cancellation suppression. If it already completed, await it or otherwise retrieve its result so no task exception is left unobserved. Perform this cleanup before the existing job-runner shutdown or at a clearly documented point in the same `finally` path, then preserve the current runner/store cleanup. The design must not attempt to force-stop the worker thread; it must ensure the asyncio task itself is no longer orphaned after lifespan exit.

9. **Keep the feature flag semantics**: Retain the existing case-insensitive disabled values `0`, `false`, and `no`, and create no task when the flag disables baseline loading.

**File**: `start.sh` (current environment setup near lines 7-24 and `main` near lines 178-184)

**Function**: startup initialization in `main`

10. **Conditionally source the local environment**: After `APP_DIR` has been resolved and before `require_commands`, add a helper or inline block that checks `[[ -f "${APP_DIR}/venv/bin/activate" ]]` and sources the file when present. Log activation only after the existing `log` function is available. Do not make the missing-file branch an error.

11. **Preserve command resolution and process flow**: Invoke activation before `require_commands`, `start_api`, and `start_streamlit`, so the activated `PATH` is used to resolve Python-based commands. Leave Ollama readiness, model caching/pull, FastAPI health polling, environment overrides, signal traps, and cleanup untouched.

12. **Do not add unrelated configuration plumbing**: The environment override belongs to `TripleExtractorConfig`, which is already constructed by the ingestion pipeline. No changes to retrieval, ingestion algorithms, baseline-loader idempotency, or unrelated deployment behavior are part of this fix.

## Testing Strategy

### Validation Approach

The strategy follows the bug-condition workflow: first capture counterexamples on the unfixed implementation, then verify the fixed behavior for all identified buggy inputs, and finally check that non-buggy behavior remains equivalent. Tests should use dependency injection and monkeypatching rather than contacting a real Ollama service or ingesting the full baseline corpus. The final repository gate is a clean `pytest -q` run.

### Exploratory Bug Condition Checking

**Goal**: Demonstrate the current failures before implementation and confirm the root causes without changing production code.

**Test Plan**:

1. Capture the timeout passed to a fake `Session.post` and assert the current default is 30.0 seconds. A fake response that would succeed only after the timeout window provides the extraction counterexample and confirms the request boundary.
2. Construct a controlled FastAPI lifespan with a baseline loader that waits on an event. Assert that the current lifespan does not enter its yielded section until the event is released, showing why health readiness is blocked.
3. Run `start.sh` with an existing `${APP_DIR}/venv/bin/activate` that exports a marker and fake Python-based commands. Confirm the marker is absent from the launched process under the current script, showing that activation is skipped.

**Expected Counterexamples**:

- The extractor sends `timeout=30.0`, and a cold-generation simulation fails or enters retry handling before the valid response is available.
- The lifespan test cannot observe yielded application readiness while the baseline loader is pending.
- The launcher reaches fake commands without the virtual-environment marker even though the activation script exists.

### Fix Checking

**Goal**: Verify that every input satisfying `isBugCondition` receives the intended corrected behavior.

**Pseudocode:**

```text
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedImplementation(input)
  ASSERT expectedBehavior(result)
END FOR
```

**Test Cases**:

- Default extractor configuration passes `120.0` to Ollama.
- A valid `OLLAMA_TIMEOUT` such as `75.5` is parsed and passed to the request.
- Invalid, non-finite, blank, and out-of-range environment values fall back safely to 120.0 and emit a warning for invalid non-blank values.
- An explicit timeout remains authoritative over the environment value.
- A fake Ollama response that succeeds on the first request records one call and no backoff sleep when completion is within the effective timeout.
- A pending baseline task does not prevent the lifespan from yielding and permits a health check after yield.
- A successful background preload logs completion; a raised exception logs failure and does not escape the lifespan; and shutdown cancellation leaves no pending task owned by the lifespan.
- The `0`, `false`, and `no` flag values create no preload task.
- An existing activation script is sourced before command checks and Python-service launch; an absent script leaves startup successful under the existing fake-command setup.

### Preservation Checking

**Goal**: Verify that for every input outside `isBugCondition`, the fixed implementation agrees with the original behavior.

**Pseudocode:**

```text
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT observableBehavior_original(input) = observableBehavior_fixed(input)
END FOR
```

**Test Plan**: Keep the current retry, parsing, health, and startup tests as the regression baseline. Add focused tests around the new seams and compare request arguments, call counts, logs, task state, process markers, and return values rather than relying only on successful completion.

**Test Cases**:

1. **Extractor retry preservation**: Reuse the existing transient-error test with failures followed by success. Assert the existing number of attempts and `[base, 2 * base, ...]` sleeps remain unchanged.
2. **Extractor parsing preservation**: Reuse evidence, canonicalization, confidence, and fallback tests to ensure only the timeout source changes.
3. **API lifecycle preservation**: Test disabled baseline startup, ordinary runner startup/shutdown, successful and failed background preload, and health component initialization.
4. **Launcher preservation**: Run existing startup script tests for directory preparation, model pull/caching, FastAPI polling, Streamlit launch, signal cleanup, and missing activation file. Add only the activation-present case.

### Unit Tests

- Extend `tests/unit/test_task18_resilience.py` or a focused extractor test module for default timeout, valid/invalid `OLLAMA_TIMEOUT`, explicit precedence, request timeout propagation, and first-attempt success.
- Add focused async lifespan tests under `tests/unit/` that fake `HybridRouter`, `bootstrap_baseline_corpus`, `asyncio.to_thread`, and `AsyncIngestionJobRunner` so readiness, exception logging, disabled flags, and cancellation can be observed deterministically.
- Keep the existing unit tests for retry backoff and extracted-triple validation unchanged as preservation checks.
- Extend `tests/test_start_script.py` with an activation-present test using a temporary `${APP_DIR}/venv/bin/activate` marker and retain the existing activation-absent scenarios.

### Property-Based Tests

- Generate supported finite timeout strings and assert each valid value becomes the exact effective request timeout, while generated malformed, non-finite, blank, and out-of-range values fall back to 120.0 without changing explicit configuration.
- Generate retry failure counts within the configured retry bound and verify the existing attempt/backoff relationship remains unchanged for non-timeout transient failures.
- Generate the supported baseline flag values and loader outcomes (success, exception, cancellation) and verify disabled flags schedule no task while enabled flags always log and clean up the task outcome.

### Integration Tests

- Run a controlled FastAPI lifespan and health request while a fake baseline preload remains pending. Verify the application is ready before the preload event is released, then verify both successful completion and failure do not take down the API.
- Run the startup script with fake Ollama, curl, uvicorn, and Streamlit commands, both with and without `${APP_DIR}/venv/bin/activate`, and verify activation ordering plus the existing readiness, model-pull, and cleanup behavior.
- Run the complete repository suite with `pytest -q`. The acceptance criterion is that all existing and newly added tests pass without requiring a live Ollama model or network service.
