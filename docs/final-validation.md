# Final Integration Validation

This report records the Task 20 validation pass for the Dynamic PDF-to-RDF Ingestion, HITL, Streamlit, and Hugging Face Spaces integration.

## Validation environment

- Host: macOS arm64
- Repository Python: `venv/bin/python` (Python 3.14.7)
- Docker: 20.10.22
- Ollama daemon/model: not available on the host during this validation
- Validation date: November 12, 2026

The repository shell does not expose global `python` or `pytest` commands. All Python commands below use the checked-in `venv` executable. Hypothesis was installed into that environment because it is declared in `requirements.txt` and was initially missing.

## Results

| Area | Command or check | Result |
| --- | --- | --- |
| Full test suite | `./venv/bin/python -m pytest -q` | **134 passed** |
| Kiro test hook | `bash .kiro/hooks/run_tests.sh --pytest tests/ -q` | **134 passed** |
| Kiro lint hook | `bash .kiro/hooks/lint_code.sh tests src app.py components core` | **Fails on 37 existing Black formatting differences; no mass reformat applied** |
| Compliance, startup, Kiro, and performance | `tests/test_compliance.py tests/test_start_script.py tests/test_task19_kiro_workflow.py tests/performance tests/unit/test_performance_optimization.py` | **30 passed** |
| Streamlit component behavior | `tests/test_hybrid_chat.py tests/test_surgeons_table.py tests/test_kg_explorer.py` | **17 passed** |
| Ontology and SHACL hook | `bash .kiro/hooks/validate_ontology.sh ontology/finance-ontology.ttl` | **Conforms: True** |
| Documentation | `./venv/bin/python -m mkdocs build --strict` | **Passed** |
| Python compilation | `./venv/bin/python -m compileall -q app.py components core src tests` | **Passed** |
| Dependency consistency | `./venv/bin/python -m pip check` | **No broken requirements** |
| Streamlit host smoke test | `streamlit run app.py ...`, then `curl http://127.0.0.1:7860/_stcore/health` | **`ok`** |
| Docker image build | `docker build --pull=false -t alchemists-chimera:task20 .` | **Passed** |
| Docker UID/runtime smoke test | Image shell checks for UID, paths, executable startup, assets | **Passed: UID 1000** |
| Streamlit in image | Container override runs Streamlit on port 7860 and probes `/_stcore/health` | **`ok`** |

The full suite is configured through `pytest.ini` with `tests/` as its test root. This excludes legacy root-level standalone scripts that are not pytest modules and previously caused collection errors.

## Integration and governance checks

- **Approved graph availability:** the default `GraphStore` loads both the ontology schema and the seeded `data/graphs/approved_kg.ttl`, so the chat has local graph facts before ingestion.
- **Hybrid transparency:** graph retrieval results are fused with source metadata and `fusion_weight`; the Streamlit chat separates graph and vector branches, displays effective `α(t)`, scores, citations, and provenance links.
- **PDF ingestion:** the integration workflow verifies PDF parsing, chunking, vector insertion, evidence grounding, provenance creation, SHACL classification, and staging.
- **Deterministic guardrails:** ungrounded evidence is rejected, low-confidence and malformed candidates are quarantined, and ontology validation conforms against `ontology/shapes.ttl`.
- **Provenance:** source document, page/chunk, evidence, extraction timestamp, and approval metadata are represented in the ingestion/staging contracts and audit trail tests.
- **Human approval:** the default pipeline obtains its staging manager through `CompatibleStagingManager(require_human_approval=True)`. Valid records remain pending until an attributed reviewer approves them. The direct lower-level `StagingManager` retains an explicit legacy auto-approval option; controlled callers must pass `require_human_approval=True`.
- **Audit transparency:** compliance tests verify hash-chained extraction, human decision, interaction, tamper detection, and attribution events.
- **Air-gapped configuration:** `AirGapVerifier` accepts loopback Ollama and local filesystem stores and rejects external LLM, SPARQL, vector, model, and telemetry endpoints.
- **Sequential Ollama inference:** triple extraction processes chunks sequentially; the pipeline may parallelize only CPU-bound entity preprocessing. The configured Ollama connection pool is size 1.
- **No login wall:** source inspection found no password, login, or authentication gate. The UI uses a sidebar demo-role selector for audit attribution.
- **Hugging Face readiness:** Docker metadata exposes port 7860, uses `appuser` UID 1000, sets `OLLAMA_MODELS=/app/.ollama/models` and `HF_HOME=/app/.cache`, creates writable `/app/data` and `/app/models`, and starts `/app/start.sh`.

## Limitations and unresolved risks

- The host did not have an Ollama daemon or `qwen2.5:3b` model available. The validation therefore did not perform a live LLM extraction or answer-generation call. Retry behavior, prompt parsing, fallback handling, and sequential-call behavior were validated with deterministic tests.
- The default Docker entrypoint was not run end-to-end because it intentionally starts Ollama and pulls `qwen2.5:3b` when the model is absent. The image build, UID/path checks, startup-script tests with fake services, and a real Streamlit-in-image health probe passed. A deployment environment must complete the first model pull before runtime is fully offline.
- The Docker build itself uses network access to install packages, download the spaCy model, and install Ollama. Runtime inference is local after those assets are cached; a public Hugging Face Space is not physically air-gapped.
- Running multiple pytest processes concurrently against the repository’s shared ChromaDB and checkpoint paths caused transient ingestion failures. The supported validation command is the sequential `pytest -q` run recorded above. Isolated temporary stores should be used for parallel CI jobs.
- The repository-wide Black check reports existing formatting differences in unrelated files. No mass reformat was applied during final integration. The modified `src/graph_store.py` has no language diagnostics, and `git diff --check` is the appropriate whitespace gate.
- The compliance utilities provide configuration and audit controls for a prototype. They do not constitute HKMA approval, formal ART certification, a security review, or a production model-risk assessment.
