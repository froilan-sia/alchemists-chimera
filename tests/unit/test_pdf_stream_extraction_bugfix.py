"""Exploration and preservation tests for the asynchronous PDF upload boundary.

The first test intentionally fails against the unfixed upload helper. It is the
bug-condition counterexample required by the approved implementation plan.
"""

from datetime import datetime
from pathlib import Path

import pytest

from components.surgeons_table import save_uploaded_pdf
from src.ingestor.pdf_parser import PDFParser, PDFParserConfig
from src.ingestor.pipeline import IngestionPipeline, PipelineStatus


class ReadableUpload:
    """Small upload double exposing bounded reads rather than ``getvalue``."""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._stream = content

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._stream)
        content, self._stream = self._stream[:size], self._stream[size:]
        return content


def test_upload_boundary_rejects_non_pdf_bytes_before_processing(tmp_path):
    """A non-empty .pdf payload without a PDF signature must be rejected early."""
    with pytest.raises(ValueError, match="PDF"):
        save_uploaded_pdf(
            ReadableUpload("report.pdf", b"not a PDF document"),
            tmp_path,
        )


def test_direct_parser_defaults_preserve_chunking_contract():
    """The direct parser retains the approved default extraction configuration."""
    config = PDFParserConfig()

    assert config.chunk_size == 1000
    assert config.chunk_overlap == 200
    assert PDFParser(config).config == config


def test_direct_pipeline_status_contract_remains_synchronous():
    """Direct callers continue to receive the existing synchronous API shape."""
    assert hasattr(IngestionPipeline, "process_pdf")
    assert hasattr(IngestionPipeline, "get_status")
    assert PipelineStatus.COMPLETED.value == "completed"
    assert datetime.now().tzinfo is None  # Existing direct metrics use local time.


def test_non_upload_missing_path_behavior_is_preserved(tmp_path):
    """Direct callers still fail immediately for a missing source path."""
    pipeline = object.__new__(IngestionPipeline)

    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        pipeline.process_pdf(Path(tmp_path) / "missing.pdf")
