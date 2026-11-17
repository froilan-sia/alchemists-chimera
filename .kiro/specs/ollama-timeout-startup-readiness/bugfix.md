# Bugfix Requirements Document

## Introduction

The local RAG service has two startup and inference bottlenecks visible in live logs. Ollama generation requests use a 30-second default timeout, so CPU-bound or cold `qwen2.5:3b` inference can fail with `Read timed out (read timeout=30.0)` and enter the existing retry sequence, producing four total request attempts for one extraction. The FastAPI lifespan also awaits the `data/input/` baseline corpus preload before yielding, which delays application readiness and prevents `GET /health` from becoming available immediately. The launcher does not automatically activate the repository virtual environment. This requirements-only bugfix is scoped to `src/ingestor/triple_extractor.py`, `src/api/main.py`, and `start.sh`; it shall preserve the existing retrieval, ingestion, health, retry, and launcher behavior outside these conditions. A newly approved test-maintenance follow-up also repairs the 12 stale full-suite tests that reference the missing `data/input/sample.pdf` fixture or the old hybrid-chat citation format. The follow-up is test-only: production logic must remain unchanged. Acceptance is defined by the expected-behavior clauses below and by a clean `./venv/bin/pytest -q` run with all 192 tests passing.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a `qwen2.5:3b` Ollama generation request runs on a CPU or loads the model cold and does not complete within 30 seconds THEN the request fails with a read-timeout error using `read timeout=30.0`.

1.2 WHEN the 30-second Ollama request timeout occurs during triple extraction THEN the existing retry policy repeats the request, resulting in four total attempts for one extraction and avoidable retry-storm latency.

1.3 WHEN the `OLLAMA_TIMEOUT` environment variable is set before the application starts THEN the triple-extraction request timeout has no documented environment-controlled configuration path and remains governed by the fixed 30-second default.

1.4 WHEN FastAPI enters its lifespan with baseline ingestion enabled THEN the lifespan awaits the synchronous `data/input/` baseline corpus preload before yielding control, so server startup and `GET /health` remain blocked until that preload completes or fails.

1.5 WHEN `start.sh` launches the services from a checkout containing `./venv/bin/activate` THEN the launcher does not automatically source that activation script before resolving and starting the Python-based services.

1.6 WHEN the full test suite runs after the original bugfix changes THEN 12 stale tests reference the missing `data/input/sample.pdf` fixture and fail before exercising their intended behavior.

1.7 WHEN the two hybrid-chat citation assertions run THEN they expect the obsolete `data/input/{file_name}#page={page}` provenance format instead of the current `/documents/{file_name}#page={page}` format.

### Expected Behavior (Correct)

2.1 WHEN no Ollama timeout override is supplied THEN the system SHALL use a 120.0-second default timeout for Ollama generation requests, allowing CPU-bound or cold `qwen2.5:3b` inference that completes within that window to finish without a read-timeout failure.

2.2 WHEN `OLLAMA_TIMEOUT` contains a valid supported timeout value before application startup THEN the system SHALL use that value for Ollama generation requests instead of 120.0 seconds.

2.3 WHEN a CPU-bound or cold `qwen2.5:3b` inference completes within the effective Ollama timeout on its first request attempt THEN the system SHALL return the successful inference result without retrying that successful request.

2.4 WHEN baseline ingestion is enabled during FastAPI lifespan startup THEN the system SHALL schedule the `data/input/` baseline corpus preload as an asyncio background task, yield the application lifespan without awaiting preload completion, and allow `GET /health` to become available without waiting for the preload to finish.

2.5 WHEN the background baseline preload completes successfully or raises an error after startup THEN the system SHALL log the completion or failure and SHALL keep the API process available; when application shutdown begins, the system SHALL manage the background task so it does not remain orphaned after the lifespan exits.

2.6 WHEN `BASELINE_INGEST_ON_STARTUP` is set to `0`, `false`, or `no` THEN the system SHALL continue to skip baseline preload scheduling.

2.7 WHEN `./venv/bin/activate` exists relative to the launcher application directory THEN `start.sh` SHALL source it before starting the Python-based services; when it does not exist, the launcher SHALL continue with its existing startup flow without failing solely because the activation script is absent.

2.8 WHEN the implementation is complete and the repository test suite is run with `pytest -q` THEN all existing tests SHALL pass.

2.9 WHEN the 12 stale full-suite tests reference the missing `data/input/sample.pdf` path THEN the tests SHALL use an existing watermarked fixture or a `tmp_path`-generated PDF according to the behavior under test, without changing production logic.

2.10 WHEN the two hybrid-chat citation assertions verify document provenance THEN the tests SHALL expect the current `/documents/{file_name}#page={page}` format.

2.11 WHEN the complete repository suite is run with `./venv/bin/pytest -q` after the follow-up test repairs THEN all 192 tests SHALL pass without requiring a live Ollama model, network service, or full baseline ingestion dependency.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a caller supplies an explicit `TripleExtractorConfig.timeout_seconds` value or an equivalent supported configuration value THEN the system SHALL CONTINUE TO honor that explicit value rather than replacing it with the default or environment value.

3.2 WHEN an Ollama request fails for a genuine transient reason after applying the effective timeout THEN the system SHALL CONTINUE to use the existing bounded retry count, exponential backoff, error handling, and failure reporting behavior.

3.3 WHEN an Ollama request completes successfully before the effective timeout THEN the system SHALL CONTINUE to parse, validate, and return extracted triples using the existing extraction behavior.

3.4 WHEN baseline ingestion is disabled by `BASELINE_INGEST_ON_STARTUP` THEN the system SHALL CONTINUE to start without loading the baseline corpus and SHALL preserve the existing API initialization and health-check behavior.

3.5 WHEN baseline ingestion is enabled and the preload is still running after the API lifespan yields THEN the system SHALL CONTINUE to expose the existing health endpoint and SHALL not make unrelated retriever, graph-store, vector-store, ingestion-worker, or response-generation components unavailable solely because baseline loading is asynchronous.

3.6 WHEN the preload encounters an exception or the application shuts down before it completes THEN the system SHALL CONTINUE to handle that condition through logging and lifespan cleanup without crashing the API process or leaving a background task running after shutdown.

3.7 WHEN `start.sh` is run with or without `./venv/bin/activate` and the existing required commands and runtime directories are available THEN the launcher SHALL CONTINUE to preserve its current Ollama readiness checks, model pull behavior, FastAPI health polling, Streamlit startup, environment-variable overrides, signal handling, and cleanup behavior.

3.8 WHEN the follow-up test repairs are made THEN production logic and production files SHALL CONTINUE to remain unchanged, and the original completed tasks SHALL remain preserved.

3.9 WHEN the repaired tests exercise behavior unrelated to the missing fixture path or obsolete citation format THEN the tests SHALL CONTINUE to assert the existing behavior and SHALL not introduce a live Ollama, network, or full-ingestion dependency.
