# Contributing

Thank you for contributing to The Alchemist's Chimera. The project is an alpha research and demonstration application for local hybrid retrieval and controlled document ingestion.

## Before making a change

1. Read the root [`README.md`](README.md) and the relevant guide under [`docs/`](docs/).
2. Check the implementation and existing tests before changing behavior.
3. Keep changes focused. Do not mix documentation work with unrelated refactors.
4. Never add private PDFs, credentials, model caches, ChromaDB files, staging records, or generated uploads to a commit.

## Development setup

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

The Streamlit app needs Ollama and `qwen2.5:3b` for live query and extraction work. Tests that exercise only pure helpers may not need a running Ollama service, but pipeline initialization still loads the spaCy model and vector-store dependencies.

## Code and documentation standards

- Follow the repository steering files under `.kiro/steering/`.
- Use type hints, focused docstrings, and specific exceptions in Python code.
- Preserve the local-first boundary. Do not add remote model calls or send document contents to third-party services without an explicit design and review.
- Keep claims in documentation tied to the current implementation. Call out prototype limitations, defaults, and separate deployment paths.
- When an API, data path, CLI command, or user-facing behavior changes, update the root README and the affected guide under `docs/`.
- Add links to new documentation from `mkdocs.yml` and check that local links resolve.

## Testing and validation

Run the relevant checks from the repository root:

```bash
pytest -q
python -m compileall -q examples
mkdocs build --strict
```

For focused changes, run a smaller test selection first, then the full applicable suite. If a check requires Ollama, Docker, a downloaded model, or a Space environment, state that dependency in the pull request rather than replacing the check with a mock that hides the integration boundary.

## Pull requests

Describe:

- what changed and why;
- the files or components affected;
- tests and documentation checks run;
- any external services, models, hardware, or network access required;
- known limitations or follow-up work.

For ingestion changes, include the evidence-grounding, validation, provenance, and staging implications. For deployment changes, include the port, UID 1000 permissions, model startup, and data-persistence implications.

## Regulatory and data handling

This project does not provide regulatory advice or certify compliance. Use synthetic or public sample data for development. Treat uploaded documents, extracted triples, logs, graph files, and vector-store contents according to the data owner's classification and retention requirements. Remove sensitive content from issue reports and pull requests.

## License

By contributing, you agree that your contribution is provided under the repository's [MIT License](LICENSE).
