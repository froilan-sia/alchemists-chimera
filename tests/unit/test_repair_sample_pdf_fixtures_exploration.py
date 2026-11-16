"""Bug-condition exploration and post-fix validation for sample PDF fixtures.

This is the original task-1 exploration test retained for task 3.4.  The
pre-fix counterexample assertions now run against the canonical source copies,
which preserve the exact malformed payloads captured before replacement.  The
same test then checks that the named PDF paths satisfy the repaired contract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

pypdf = pytest.importorskip("pypdf")
from pypdf import PdfReader

from src.ingestor.pdf_parser import PDFParser


REPOSITORY_ROOT = Path(__file__).parents[2]
INPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "input"
SOURCE_DIRECTORY = INPUT_DIRECTORY / "fixture_sources"
README_PATH = INPUT_DIRECTORY / "SAMPLE_DATA_README.md"

NAMED_FIXTURES = (
    {
        "filename": "hkma_capital_requirements.pdf",
        "source_filename": "hkma_capital_requirements.txt",
        "title": "HKMA Supervisory Policy Manual SA-2: Capital Adequacy Requirements",
        "expected_size": 5358,
        "expected_sha256": "45812d239aea4092387bee3939d6cfb2812edbfe308c07e99d031d2997544426",
        "expected_last_line": "Revision: SA-2.5",
        "markers": (
            "4.5%",
            "6.0%",
            "8.0%",
            "2.5%",
            "3%",
            "100%",
            "Hong Kong Monetary Authority",
            "authorized institutions",
        ),
    },
    {
        "filename": "basel_iii_framework.pdf",
        "source_filename": "basel_iii_framework.txt",
        "title": "Basel III: International Regulatory Framework for Banks",
        "expected_size": 5163,
        "expected_sha256": "e9b8eb8c9e6de16fe039bc2fe1d3101d9364d25a5c7d35a0e96a1c4467186131",
        "expected_last_line": "Effective Date: Various, with full implementation by January 1, 2023",
        "markers": (
            "4.5%",
            "6.0%",
            "8.0%",
            "2.5%",
            "3%",
            "100%",
            "72.5%",
            "Basel Committee on Banking Supervision",
            "G-SIBs",
            "D-SIBs",
        ),
    },
    {
        "filename": "risk_weighted_assets.pdf",
        "source_filename": "risk_weighted_assets.txt",
        "title": "Risk-Weighted Assets: Calculation Methodology and Regulatory Requirements",
        "expected_size": 4795,
        "expected_sha256": "19e1eff663e8e0810538499227c12a6317cf8d2d724b3ae1a389668aaf03f871",
        "expected_last_line": "Effective Date: January 1, 2022",
        "markers": (
            "credit risk",
            "market risk",
            "operational risk",
            "PD",
            "LGD",
            "EAD",
            "15%",
            "1,250%",
            "Financial Stability Board",
            "Basel Committee on Banking Supervision",
        ),
    },
)


def _normalize_extracted_text(text: str) -> str:
    """Normalize extracted PDF whitespace for the bug-condition predicate."""
    return " ".join(text.split())


def is_bug_condition(
    *,
    path: Path,
    payload: bytes,
    reader_error: str | None,
    page_count: int,
    extracted_text: str,
) -> bool:
    """Return whether a named fixture exhibits the documented defect."""
    named_fixture = path.name in {item["filename"] for item in NAMED_FIXTURES}
    invalid_signature = not payload.startswith(b"%PDF-")
    unreadable = reader_error is not None
    missing_extraction = page_count < 1 or not _normalize_extracted_text(extracted_text)
    return named_fixture and (invalid_signature or unreadable or missing_extraction)


def _inspect_fixture(
    case: dict[str, Any], *, payload_path: Path | None = None
) -> dict[str, Any]:
    """Capture one fixture's bytes, text identity, and strict-reader result.

    ``payload_path`` lets the retained pre-fix assertions inspect the exact
    canonical source bytes while keeping the logical path in the named fixture
    set, just as the original exploration test did before replacement.
    """
    path = INPUT_DIRECTORY / case["filename"]
    actual_path = payload_path or path
    payload = actual_path.read_bytes()
    try:
        payload_text: str | None = payload.decode("utf-8")
    except UnicodeDecodeError:
        payload_text = None

    reader_error: str | None = None
    extracted_text = ""
    page_count = 0
    try:
        reader = PdfReader(actual_path, strict=True)
        page_count = len(reader.pages)
        extracted_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except Exception as error:  # pypdf exposes PdfReadError across versions.
        reader_error = f"{type(error).__name__}: {error}"

    return {
        "path": path,
        "actual_path": actual_path,
        "payload": payload,
        "payload_text": payload_text,
        "reader_error": reader_error,
        "page_count": page_count,
        "extracted_text": extracted_text,
        "bug_condition": is_bug_condition(
            path=path,
            payload=payload,
            reader_error=reader_error,
            page_count=page_count,
            extracted_text=extracted_text,
        ),
    }


def _counterexample_message(observation: dict[str, Any]) -> str:
    """Format a reproducible pre-fix counterexample for pytest output."""
    payload = observation["payload"]
    payload_text = observation["payload_text"]
    lines = payload_text.splitlines() if payload_text is not None else ["<binary payload>"]
    return (
        f"{observation['path'].relative_to(REPOSITORY_ROOT)}: "
        f"first_line={lines[0]!r}; starts_with_pdf="
        f"{payload.startswith(b'%PDF-')}; bytes={len(payload)}; "
        f"sha256={hashlib.sha256(payload).hexdigest()}; "
        f"last_line={lines[-1]!r}; reader_error={observation['reader_error']!r}; "
        f"page_count={observation['page_count']}; extracted_text_empty="
        f"{not _normalize_extracted_text(observation['extracted_text'])}"
    )


def test_named_fixtures_satisfy_pdf_contract_and_capture_bug_counterexamples():
    """Retained exploration checks now prove the repaired behavior."""
    readme = README_PATH.read_text(encoding="utf-8")
    pre_fix_counterexamples = []
    fixed_counterexamples = []

    for case in NAMED_FIXTURES:
        # Preserve the original task-1 assertions and evidence against the
        # canonical copies captured before replacement.  These source files
        # are the auditable record of the malformed pre-fix payloads.
        source_observation = _inspect_fixture(
            case, payload_path=SOURCE_DIRECTORY / case["source_filename"]
        )
        source_payload = source_observation["payload"]
        source_text = source_observation["payload_text"]
        assert source_text is not None
        source_lines = source_text.splitlines()
        assert source_payload == source_text.encode("utf-8")
        assert len(source_payload) == case["expected_size"]
        assert hashlib.sha256(source_payload).hexdigest() == case["expected_sha256"]
        assert source_lines[0] == case["title"]
        assert source_lines[-1] == case["expected_last_line"]
        assert not source_payload.startswith(b"%PDF-")
        assert source_observation["bug_condition"], _counterexample_message(
            source_observation
        )
        pre_fix_counterexamples.append(_counterexample_message(source_observation))

        # Validate the same named path after the PDF replacement.
        observation = _inspect_fixture(case)
        payload = observation["payload"]
        extracted_text = observation["extracted_text"]
        assert payload.startswith(b"%PDF-1.4")
        assert payload.rstrip().endswith(b"%%EOF")
        assert observation["reader_error"] is None, _counterexample_message(observation)
        assert observation["page_count"] >= 1
        assert _normalize_extracted_text(extracted_text)
        assert _normalize_extracted_text(extracted_text) == _normalize_extracted_text(
            source_text
        )
        assert all(marker in extracted_text for marker in case["markers"])

        chunks = PDFParser().parse_pdf(observation["path"])
        assert chunks
        assert all(chunk.text.strip() for chunk in chunks)
        assert all(chunk.page_number >= 1 for chunk in chunks)
        assert all(chunk.metadata["page_text_length"] > 0 for chunk in chunks)
        assert all(chunk.document_name == case["filename"] for chunk in chunks)
        assert all(chunk.metadata["document_name"] == case["filename"] for chunk in chunks)

        if observation["bug_condition"]:
            fixed_counterexamples.append(_counterexample_message(observation))

        # The README still presents each repaired path under its original name.
        assert case["filename"] in readme
        assert "### PDF Documents" in readme

    # The original pre-fix evidence remains represented, while no scoped
    # counterexample remains at the repaired named paths.
    assert len(pre_fix_counterexamples) == len(NAMED_FIXTURES)
    assert not fixed_counterexamples, "Remaining bug-condition counterexamples:\n" + "\n".join(
        fixed_counterexamples
    )
