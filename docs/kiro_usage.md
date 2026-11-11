# Kiro-assisted development

This page records the Kiro workflow used to implement the PDF-to-RDF ingestion feature. The `.kiro/specs/dynamic-pdf-rdf-ingestion-hitl-streamlit/` directory is the source of truth for requirements, design decisions, and task progress.

## Spec-driven implementation

The implementation follows the Task 19 checklist in `tasks.md`:

1. Requirements and design were read before changing the ingestion modules.
2. Existing source interfaces and tests were inspected before adding compatibility contracts.
3. Hook behavior was exercised with the repository virtual environment.
4. Tests and documentation changes were kept scoped to Kiro integration.
5. The task file records the completed integration work and known validation limits.

The ingestion components retain their established runtime interfaces in `src/ingestor/`. The additive Pydantic contracts in `src/models.py` provide a stable serialization boundary for document uploads, extraction progress, staged triples, entities, provenance, validation results, and extraction summaries.

## Steering files

The implementation follows the repository steering files:

- `.kiro/steering/coding_standards.md` for type hints, Pydantic models, docstrings, error handling, and test placement.
- `.kiro/steering/project_guidelines.md` for local-first processing, dependency injection, provenance, hybrid retrieval, and resource-aware async patterns.
- `.kiro/steering/kiro_workflow.md` for spec tracking, hook automation, AI-assisted review, and documentation.

## Automated hooks

The JSON hook definitions are portable within a checkout and delegate interpreter selection to small shell runners:

| Hook | Trigger | Runner | Purpose |
| --- | --- | --- | --- |
| `validate-ontology.json` | Save a Turtle file | `validate_ontology.sh` | Validate the checked-in finance ontology against its SHACL shapes. |
| `run-tests.json` | Save a Python file | `run_tests.sh` | Run `pytest tests/ -xvs --tb=short`. |
| `lint-code.json` | Save a Python file | `lint_code.sh` | Run Black, isort, and flake8 for the saved file or requested target. |

The runners prefer `KIRO_PYTHON_BIN`, then `venv/bin/python`, then `python` or `python3`. The ontology runner similarly prefers `KIRO_PYSHACL_BIN` and the repository virtual environment. Hooks do not install packages implicitly.

When a Kiro hook invokes the lint runner with `.` and provides `KIRO_FILE_PATH`, the runner checks that saved file only. Running the same command manually with no file context checks the whole repository, which can expose formatting debt in older or user-modified files.

Run the focused checks from the repository root:

```bash
KIRO_FILE_PATH=tests/test_task19_kiro_workflow.py \
  bash .kiro/hooks/lint_code.sh .

bash .kiro/hooks/validate_ontology.sh ontology/finance-ontology.ttl

bash .kiro/hooks/run_tests.sh --pytest tests/test_kiro_hooks.py tests/test_task19_kiro_workflow.py -q
```

## Interface and test coverage

`tests/test_kiro_hooks.py` checks the JSON schema and hook wiring. `tests/test_task19_kiro_workflow.py` checks portable runner paths, shell syntax, ontology hook execution, focused lint execution, and compatibility of the new Pydantic contracts with the existing `QueryRequest` model.

The full suite remains the final quality gate. Tests that require Ollama, an installed spaCy model, Docker, or a pre-existing vector database need those local services and artifacts. A hook failure should be reported with its environment dependency rather than hidden by replacing the integration boundary with a fake implementation.

## Kiro-assisted change record

Task 19 used Kiro to inspect the requirements, design, existing source, steering files, hook definitions, and tests before editing. Kiro then generated the scoped hook runners, compatibility models, tests, documentation links, and spec progress note. The resulting changes are reviewable in the repository diff and are validated by the focused tests listed above.
