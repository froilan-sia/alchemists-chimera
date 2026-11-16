"""Preservation checks for the sample PDF fixture repair.

These checks deliberately establish the behavior of the unfixed checkout before
any canonical source files or replacement PDFs exist.  They cover repository
content, the direct parser contract, out-of-scope fixture bytes, generation
scope, and the offline boundary.
"""

from __future__ import annotations

import hashlib
import http.client
import socket
import urllib.request
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st
from pypdf import PdfReader

from src.ingestor.pdf_parser import PDFParser, PDFParserError

REPOSITORY_ROOT = Path(__file__).parents[2]
INPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "input"
README_PATH = INPUT_DIRECTORY / "SAMPLE_DATA_README.md"
PARSER_PATH = REPOSITORY_ROOT / "src" / "ingestor" / "pdf_parser.py"
GENERATOR_PATH = REPOSITORY_ROOT / "tools" / "generate_sample_pdf_fixtures.py"

NAMED_FIXTURE_FILENAMES = frozenset(
    {
        "hkma_capital_requirements.pdf",
        "basel_iii_framework.pdf",
        "risk_weighted_assets.pdf",
    }
)

# These are the only paths the planned generator may replace.  Keeping this
# mapping explicit makes an accidental broad output glob observable before the
# generator is implemented.
EXPECTED_GENERATOR_OUTPUTS = frozenset(
    INPUT_DIRECTORY / filename for filename in NAMED_FIXTURE_FILENAMES
)
PROTECTED_PATHS = frozenset(
    {
        INPUT_DIRECTORY / "SAMPLE_DATA_README.md",
        INPUT_DIRECTORY / "sample.pdf",
        INPUT_DIRECTORY / "test_hkma_basel.pdf",
        PARSER_PATH,
    }
)

README_REQUIREMENTS = (
    "hkma_capital_requirements.pdf",
    "basel_iii_framework.pdf",
    "risk_weighted_assets.pdf",
    "HKMA Supervisory Policy Manual SA-2 on capital adequacy requirements",
    "Basel III international regulatory framework",
    "Risk-weighted assets calculation methodology",
    "CET1 ratio, Tier 1 capital, total capital ratio, leverage ratio, liquidity coverage ratio",
    "Capital buffers, leverage ratio, liquidity standards, risk coverage",
    "Credit risk RWA, market risk RWA, operational risk RWA",
    "HKMA, banks, authorized institutions",
    "Basel Committee, G-SIBs, D-SIBs",
    "Financial Stability Board, banks with internal models",
    '"What are the capital requirements for HSBC Hong Kong?"',
    '"How are risk-weighted assets calculated for credit risk?"',
    "Upload PDFs to Surgeon's Table tab",
    "Extract triples with proper provenance",
    "Verify air-gapped operation",
)

# These baselines cover the two pre-existing PDFs that are now included in
# the requested watermark set.  They make accidental rewrites observable while
# recording their new valid, standalone PDF behavior.
UNRELATED_FIXTURE_BASELINES = {
    "sample.pdf": {
        "sha256": "49f6da1182995d3b9e0381f194423279c5e5043385cb3998f4505f6616bfe893",
        "size": 10354002,
        "pdf_readable": True,
        "parser_readable": True,
    },
    "test_hkma_basel.pdf": {
        "sha256": "49d668dd22a936a6f7adc729fe1ea6fb7eb8050df8b5c27a1bd578a42b780fa6",
        "size": 15665,
        "pdf_readable": True,
        "parser_readable": True,
    },
}


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a repository artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_readme_references_and_documentation_contract_are_preserved():
    """The README keeps paths, concepts, entities, queries, and instructions."""
    readme = README_PATH.read_text(encoding="utf-8")

    for filename in NAMED_FIXTURE_FILENAMES:
        assert filename in readme
    assert "### PDF Documents" in readme
    assert "## Sample Queries for Testing" in readme
    assert "## Usage for Testing PDF Ingestion Pipeline" in readme

    for requirement in README_REQUIREMENTS:
        assert requirement in readme


@given(requirement=st.sampled_from(README_REQUIREMENTS))
def test_readme_preservation_requirements_hold_for_each_documented_item(
    requirement: str,
):
    """Property: every recorded README contract item remains present."""
    readme = README_PATH.read_text(encoding="utf-8")

    assert requirement in readme


@pytest.mark.parametrize("filename", sorted(UNRELATED_FIXTURE_BASELINES))
def test_unrelated_fixture_bytes_and_observed_readability_are_preserved(
    filename: str,
):
    """Unrelated fixture bytes and their current reader behavior stay stable."""
    baseline = UNRELATED_FIXTURE_BASELINES[filename]
    path = INPUT_DIRECTORY / filename

    assert path.exists()
    assert path not in EXPECTED_GENERATOR_OUTPUTS
    assert path.stat().st_size == baseline["size"]
    assert _sha256(path) == baseline["sha256"]

    reader_error = None
    try:
        reader = PdfReader(path, strict=True)
        assert baseline["pdf_readable"] is True
        assert len(reader.pages) > 0
        assert any((page.extract_text() or "").strip() for page in reader.pages)
    except Exception as error:  # pypdf's concrete error varies by version.
        reader_error = error

    if baseline["pdf_readable"]:
        assert reader_error is None
    else:
        assert reader_error is not None

    parser_error = None
    try:
        chunks = PDFParser().parse_pdf(path)
        assert baseline["parser_readable"] is True
        assert chunks
        assert any(chunk.text.strip() for chunk in chunks)
    except (PDFParserError, FileNotFoundError) as error:
        parser_error = error

    if baseline["parser_readable"]:
        assert parser_error is None
    else:
        assert isinstance(parser_error, PDFParserError)


@pytest.mark.parametrize("filename", sorted(NAMED_FIXTURE_FILENAMES))
def test_generator_scope_excludes_protected_repository_paths(filename: str):
    """Property: planned output targets cannot include protected paths."""
    output_path = INPUT_DIRECTORY / filename

    assert output_path in EXPECTED_GENERATOR_OUTPUTS
    assert EXPECTED_GENERATOR_OUTPUTS.isdisjoint(PROTECTED_PATHS)
    assert output_path not in PROTECTED_PATHS

    # The source and output names must remain the same, so callers keep using
    # the README's existing paths after the format-only repair.
    assert output_path.name == filename


@pytest.mark.parametrize("protected_path", sorted(PROTECTED_PATHS, key=str))
def test_generator_scope_does_not_target_protected_files(protected_path: Path):
    """Protected README, parser, and unrelated fixtures are out of scope."""
    assert protected_path.exists()
    assert protected_path not in EXPECTED_GENERATOR_OUTPUTS

    # Once task 3 adds the generator, this check also prevents it from being
    # mistaken for a protected file by requiring only the three named outputs.
    if GENERATOR_PATH.exists():
        generator_text = GENERATOR_PATH.read_text(encoding="utf-8")
        assert protected_path.name not in generator_text


@given(filename=st.sampled_from(tuple(sorted(NAMED_FIXTURE_FILENAMES))))
def test_named_output_mapping_is_closed_over_the_three_fixture_paths(
    filename: str,
):
    """Property: every generated output is one of the three named fixtures."""
    candidate = INPUT_DIRECTORY / filename

    assert candidate in EXPECTED_GENERATOR_OUTPUTS
    assert candidate not in PROTECTED_PATHS
    assert len(EXPECTED_GENERATOR_OUTPUTS) == 3


def test_pdf_parser_public_contract_is_preserved_on_valid_pdf():
    """The direct parser keeps its existing chunks and metadata semantics."""
    path = INPUT_DIRECTORY / "sample.pdf"
    parser = PDFParser()
    chunks = parser.parse_pdf(path)

    assert parser.config.chunk_size == 1000
    assert parser.config.chunk_overlap == 200
    assert parser.config.remove_extra_whitespace is True
    assert chunks

    reader = PdfReader(path, strict=True)
    total_pages = len(reader.pages)
    expected_fields = {
        "id",
        "text",
        "page_number",
        "chunk_index",
        "total_chunks",
        "metadata",
        "start_char",
        "end_char",
        "document_id",
        "document_name",
    }

    for chunk in chunks:
        assert set(vars(chunk)) == expected_fields
        assert chunk.text.strip()
        assert 1 <= chunk.page_number <= total_pages
        assert chunk.chunk_index >= 0
        assert chunk.total_chunks >= 1
        assert chunk.id.endswith(
            f"-page{chunk.page_number:03d}-chunk{chunk.chunk_index:03d}"
        )
        assert chunk.document_name == path.name
        assert chunk.document_id
        assert chunk.metadata["document_id"] == chunk.document_id
        assert chunk.metadata["document_name"] == path.name
        assert chunk.metadata["total_pages"] == total_pages
        assert chunk.start_char >= 0
        assert chunk.end_char > chunk.start_char
        assert chunk.end_char - chunk.start_char == len(chunk.text)
        assert chunk.metadata["page_text_length"] >= chunk.end_char

    chunks_by_page = {}
    for chunk in chunks:
        chunks_by_page.setdefault(chunk.page_number, []).append(chunk)
    for page_chunks in chunks_by_page.values():
        assert [chunk.chunk_index for chunk in page_chunks] == list(
            range(len(page_chunks))
        )
        assert all(chunk.total_chunks == len(page_chunks) for chunk in page_chunks)


def test_preservation_checks_require_no_network_or_external_pdf_services(monkeypatch):
    """Local validation succeeds when common network boundaries are blocked."""

    def deny_network(*args, **kwargs):
        raise AssertionError("preservation checks attempted network access")

    monkeypatch.setattr(socket, "socket", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(urllib.request, "urlopen", deny_network)
    monkeypatch.setattr(http.client, "HTTPConnection", deny_network)
    monkeypatch.setattr(http.client, "HTTPSConnection", deny_network)

    readme = README_PATH.read_text(encoding="utf-8")
    assert all(filename in readme for filename in NAMED_FIXTURE_FILENAMES)

    path = INPUT_DIRECTORY / "sample.pdf"
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) > 0
    assert any((page.extract_text() or "").strip() for page in reader.pages)
    assert PDFParser().parse_pdf(path)
