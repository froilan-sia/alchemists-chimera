"""Bug-condition exploration for the malformed sample PDF fixtures.

This module intentionally runs against the current checkout before any fixture
repair.  It records the exact UTF-8 payload fingerprints and PDF-reader
failures, then asserts the contract that the later repair must satisfy.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

pypdf = pytest.importorskip("pypdf")
from pypdf import PdfReader


REPOSITORY_ROOT = Path(__file__).parents[2]
INPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "input"
README_PATH = INPUT_DIRECTORY / "SAMPLE_DATA_README.md"

NAMED_FIXTURES = (
    {
        "filename": "hkma_capital_requirements.pdf",
        "title": "HKMA Supervisory Policy Manual SA-2: Capital Adequacy Requirements",
        "expected_size": 5358,
        "expected_sha256": "45812d239aea4092387bee3939d6cfb2812edbfe308c07e99d031d2997544426",
        "expected_last_line": "Revision: SA-2.5",
    },
    {
        "filename": "basel_iii_framework.pdf",
        "title": "Basel III: International Regulatory Framework for Banks",
        "expected_size": 5163,
        "expected_sha256": "e9b8eb8c9e6de16fe039bc2fe1d3101d9364d25a5c7d35a0e96a1c4467186131",
        "expected_last_line": "Effective Date: Various, with full implementation by January 1, 2023",
    },
    {
        "filename": "risk_weighted_assets.pdf",
        "title": "Risk-Weighted Assets: Calculation Methodology and Regulatory Requirements",
        "expected_size": 4795,
        "expected_sha256": "19e1eff663e8e0810538499227c12a6317cf8d2d724b3ae1a389668aaf03f871",
        "expected_last_line": "Effective Date: January 1, 2022",
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


def _inspect_fixture(case: dict[str, Any]) -> dict[str, Any]:
    """Capture one fixture's bytes, text identity, and strict-reader result."""
    path = INPUT_DIRECTORY / case["filename"]
    payload = path.read_bytes()
    payload_text = payload.decode("utf-8")

    reader_error: str | None = None
    extracted_text = ""
    page_count = 0
    try:
        reader = PdfReader(path, strict=True)
        page_count = len(reader.pages)
        extracted_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except Exception as error:  # pypdf exposes PdfReadError across versions.
        reader_error = f"{type(error).__name__}: {error}"

    return {
        "path": path,
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
    lines = observation["payload_text"].splitlines()
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
    """The unfixed fixtures expose all reproducible format counterexamples."""
    readme = README_PATH.read_text(encoding="utf-8")
    observations = []

    for case in NAMED_FIXTURES:
        observation = _inspect_fixture(case)
        payload = observation["payload"]
        payload_text = observation["payload_text"]
        lines = payload_text.splitlines()

        # These checks capture the exact current local UTF-8 payload without
        # rewriting it.  They protect title, section order, and ending content
        # while the later task copies the bytes into canonical source fixtures.
        assert payload == payload_text.encode("utf-8")
        assert len(payload) == case["expected_size"]
        assert hashlib.sha256(payload).hexdigest() == case["expected_sha256"]
        assert lines[0] == case["title"]
        assert lines[-1] == case["expected_last_line"]
        assert not payload.startswith(b"%PDF-")

        # The README still presents each plain-text payload as a PDF fixture.
        assert case["filename"] in readme
        assert "### PDF Documents" in readme

        if observation["bug_condition"]:
            observations.append(_counterexample_message(observation))

    # This is the expected-to-fail assertion on the unfixed checkout.  Keeping
    # it as the final aggregate assertion reports every scoped counterexample
    # instead of stopping after the first malformed fixture.
    assert not observations, "Bug-condition counterexamples:\n" + "\n".join(observations)
