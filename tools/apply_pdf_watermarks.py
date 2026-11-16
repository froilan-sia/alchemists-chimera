"""Apply the demo watermark to every PDF in the local input fixture set.

The watermark is rendered as semi-transparent vector artwork rather than PDF
text. This keeps the exact regulatory text available to pypdf extraction while
making the notice visible in a normal PDF viewer.
"""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from tools.generate_sample_pdf_fixtures import (
    WATERMARK_TEXT,
    build_pdf,
    build_watermark_pdf,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "input"
TARGET_FILENAMES = (
    "basel_iii_framework.pdf",
    "hkma_capital_requirements.pdf",
    "risk_weighted_assets.pdf",
    "sample.pdf",
    "test_hkma_basel.pdf",
)


def _replace_atomically(path: Path, payload: bytes) -> None:
    """Replace one fixture with complete bytes written beside the source."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _watermark_valid_pdf(path: Path) -> None:
    """Add the watermark beneath the existing content of every page."""
    reader = PdfReader(path, strict=True)
    writer = PdfWriter()
    overlays: dict[tuple[float, float], object] = {}

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        dimensions = (width, height)
        if dimensions not in overlays:
            overlay_reader = PdfReader(
                BytesIO(build_watermark_pdf(width, height)), strict=True
            )
            overlays[dimensions] = overlay_reader.pages[0]
        target_page = writer.add_page(page)
        target_page.merge_page(overlays[dimensions], over=False)

    output = BytesIO()
    writer.add_metadata({"/Watermark": WATERMARK_TEXT})
    writer.write(output)
    _replace_atomically(path, output.getvalue())


def _convert_text_fixture(path: Path) -> None:
    """Convert the legacy text fixture into a standalone watermarked PDF."""
    source_text = path.read_text(encoding="utf-8")
    _replace_atomically(path, build_pdf(source_text))


def apply_watermarks(input_directory: Path | str = INPUT_DIRECTORY) -> tuple[Path, ...]:
    """Watermark all five requested input files and return their paths."""
    directory = Path(input_directory)
    processed: list[Path] = []
    for filename in TARGET_FILENAMES:
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"target PDF fixture not found: {path}")
        if WATERMARK_TEXT.encode("ascii") in path.read_bytes():
            processed.append(path)
            continue
        try:
            reader = PdfReader(path, strict=True)
        except Exception:
            _convert_text_fixture(path)
        else:
            if reader.metadata and reader.metadata.get("/Watermark") == WATERMARK_TEXT:
                processed.append(path)
                continue
            _watermark_valid_pdf(path)
        processed.append(path)
    return tuple(processed)


def main() -> int:
    """Run watermarking for the repository's checked-in input fixtures."""
    for path in apply_watermarks():
        print(f"watermarked {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
