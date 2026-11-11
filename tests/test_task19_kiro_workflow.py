"""Focused integration checks for the Task 19 Kiro workflow."""

import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from src.models import (
    DocumentChunk,
    DocumentUpload,
    Entity,
    ExtractedTriple,
    ExtractionResult,
    ExtractionStatus,
    ProvenancedTriple,
    QueryRequest,
    StagingTriple,
    ValidationResult,
)

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".kiro" / "hooks"


def _hook_command(name: str) -> str:
    """Return one configured Kiro hook command."""
    path = HOOKS / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["hooks"][0]["action"]["command"]


def test_hook_runners_are_executable_and_syntactically_valid() -> None:
    """Portable shell runners are executable and parse with Bash."""
    for name in ("run_tests.sh", "lint_code.sh", "validate_ontology.sh"):
        path = HOOKS / name
        assert path.stat().st_mode & stat.S_IXUSR
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_hook_commands_do_not_embed_the_authoring_machine_path() -> None:
    """Hook commands resolve the workspace at runtime."""
    for name in ("validate-ontology.json", "run-tests.json", "lint-code.json"):
        assert "/Users/" not in _hook_command(name)


def test_ontology_hook_executes_against_repository_files() -> None:
    """The ontology hook validates the checked-in ontology and shapes."""
    pyshacl = ROOT / "venv" / "bin" / "pyshacl"
    if not pyshacl.exists() and shutil.which("pyshacl") is None:
        pytest.skip("pyshacl is not installed")

    result = subprocess.run(
        [
            "bash",
            str(HOOKS / "validate_ontology.sh"),
            "ontology/finance-ontology.ttl",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ontology validation passed" in result.stdout


def test_lint_hook_checks_a_saved_python_target() -> None:
    """The lint hook can validate one saved file without rewriting it."""
    target = ROOT / "tests" / "test_task19_kiro_workflow.py"
    result = subprocess.run(
        ["bash", str(HOOKS / "lint_code.sh"), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_ingestion_contracts_follow_existing_pydantic_model_patterns() -> None:
    """Ingestion contracts follow the core query model conventions."""
    query = QueryRequest(query="What is the capital requirement?")
    upload = DocumentUpload(file_name="sample.pdf", file_content=b"%PDF")
    status = ExtractionStatus(
        document_id="doc-1",
        status="COMPLETE",
        progress=1.0,
    )
    chunk = DocumentChunk(
        chunk_id="doc-1-page001-chunk000",
        content="The bank must maintain capital.",
        document_name="sample.pdf",
        page_number=1,
        chunk_index=0,
    )
    entity = Entity(
        text="The Bank",
        label="ORG",
        start_char=0,
        end_char=8,
        confidence=0.9,
    )
    triple = ExtractedTriple(
        subject="chimera:Bank",
        predicate="chimera:hasRequirement",
        object="chimera:Capital",
        evidence_quote="The bank must maintain capital.",
        chunk_id=chunk.chunk_id,
        page_number=chunk.page_number,
        entity_anchors=[entity.text],
    )
    staged = StagingTriple(
        id="triple-1",
        subject=triple.subject,
        predicate=triple.predicate,
        object=triple.object,
        evidence_quote=triple.evidence_quote,
        shacl_status="VALID",
        source_document=upload.file_name,
        page_number=chunk.page_number,
    )
    provenanced = ProvenancedTriple(
        triple=triple,
        provenance_uri="chimera:provenance/triple-1",
        source_document=upload.file_name,
        extraction_method="ollama:qwen2.5:3b",
        validation_status=staged.shacl_status,
    )
    validation = ValidationResult(is_valid=True, severity="INFO")
    result = ExtractionResult(
        chunks_processed=1,
        triples_extracted=1,
        valid_triples=1,
        quarantined_triples=0,
    )

    assert query.query
    assert upload.model_dump()["file_name"] == "sample.pdf"
    assert status.progress == 1.0
    assert chunk.page_number == 1
    assert entity.label == "ORG"
    assert provenanced.triple.evidence_quote in chunk.content
    assert validation.validation_errors == []
    assert result.errors == []
