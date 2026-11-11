"""Performance checks for PDF parsing and chunk generation."""

from pathlib import Path
from time import perf_counter

import pytest

pytest.importorskip("pypdf")
pytest.importorskip("pydantic")

from src.ingestor.pdf_parser import PDFParser, PDFParserConfig

SAMPLE_PDF = Path(__file__).parents[2] / "data" / "input" / "sample.pdf"


def test_sample_pdf_parsing_completes_within_five_minutes():
    """The parser meets the five-minute requirement for a regulatory sample PDF."""
    parser = PDFParser(PDFParserConfig(chunk_size=1000, chunk_overlap=200))

    started = perf_counter()
    chunks = parser.parse_pdf(SAMPLE_PDF)
    elapsed = perf_counter() - started

    assert chunks
    assert elapsed < 300
    assert all(chunk.text for chunk in chunks)
    assert all(chunk.page_number >= 1 for chunk in chunks)


def test_streaming_parser_matches_batch_chunk_count():
    """Streaming parsing produces the same number of chunks without accumulation errors."""
    parser = PDFParser(PDFParserConfig(chunk_size=1000, chunk_overlap=200))

    batch_chunks = parser.parse_pdf(SAMPLE_PDF)
    stream_chunks = list(parser.parse_pdf_streaming(SAMPLE_PDF))

    assert len(stream_chunks) == len(batch_chunks)
    assert [chunk.id for chunk in stream_chunks] == [chunk.id for chunk in batch_chunks]
