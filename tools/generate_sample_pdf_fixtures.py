"""Generate deterministic PDF fixtures from canonical local source text.

The generator intentionally has no third-party or network dependencies.  Its
only outputs are the three named regulatory fixture PDFs, and its canonical
source files are never modified.
"""

from __future__ import annotations

import argparse
import math
import textwrap
from pathlib import Path
from typing import Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIRECTORY = REPOSITORY_ROOT / "data" / "input" / "fixture_sources"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "input"

# This closed mapping is the generator's output contract.  Do not broaden it:
# callers and README references rely on these exact filenames.
FIXTURE_MAPPING: dict[str, str] = {
    "hkma_capital_requirements.pdf": "hkma_capital_requirements.txt",
    "basel_iii_framework.pdf": "basel_iii_framework.txt",
    "risk_weighted_assets.pdf": "risk_weighted_assets.txt",
}

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 72
TOP_MARGIN = 72
FONT_SIZE = 10
LEADING = 14
MAX_LINE_WIDTH = 88
LINES_PER_PAGE = 48
PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
WATERMARK_TEXT = "FICTIONAL DOCUMENT - for demo purpose only"
WATERMARK_GRAY = 0.58
WATERMARK_ALPHA = 0.20
WATERMARK_ANGLE_DEGREES = 35.0
WATERMARK_GLYPHS: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "a": ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    "d": ("00001", "00001", "01111", "10001", "10001", "10001", "01111"),
    "e": ("00000", "00000", "01110", "10001", "11111", "10000", "01110"),
    "f": ("00110", "01001", "01000", "11100", "01000", "01000", "01000"),
    "m": ("00000", "00000", "11010", "10101", "10101", "10101", "10101"),
    "n": ("00000", "00000", "11110", "10001", "10001", "10001", "10001"),
    "o": ("00000", "00000", "01110", "10001", "10001", "10001", "01110"),
    "l": ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    "p": ("00000", "00000", "11110", "10001", "11110", "10000", "10000"),
    "r": ("00000", "00000", "10111", "11000", "10000", "10000", "10000"),
    "s": ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    "u": ("00000", "00000", "10001", "10001", "10001", "10011", "01101"),
    "y": ("00000", "00000", "10001", "10001", "01111", "00001", "01110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
}


class FixtureGenerationError(RuntimeError):
    """Base error for invalid fixture-generation requests."""


class UnsupportedFixtureMappingError(FixtureGenerationError, ValueError):
    """Raised when a requested output is outside the closed fixture mapping."""


class MissingCanonicalSourceError(FixtureGenerationError, FileNotFoundError):
    """Raised when a mapped canonical source file is unavailable."""


def normalize_source_text(source_text: str) -> str:
    """Normalize only newline conventions for deterministic PDF layout.

    The source file itself remains byte-for-byte unchanged.  This normalized
    value is used only to split the text into layout lines.
    """
    return source_text.replace("\r\n", "\n").replace("\r", "\n")


def _wrapped_lines(source_text: str) -> list[str]:
    """Return fixed-width lines while retaining every source word and blank."""
    lines: list[str] = []
    for source_line in normalize_source_text(source_text).split("\n"):
        if not source_line:
            lines.append("")
            continue

        wrapped = textwrap.wrap(
            source_line,
            width=MAX_LINE_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
            drop_whitespace=True,
            replace_whitespace=False,
        )
        # A whitespace-only paragraph is still a source blank line.
        lines.extend(wrapped or [""])
    return lines or [""]


def _paginate(lines: Sequence[str]) -> list[list[str]]:
    """Split layout lines into deterministic pages with fixed capacity."""
    return [
        list(lines[start : start + LINES_PER_PAGE])
        for start in range(0, len(lines), LINES_PER_PAGE)
    ] or [[]]


def _escape_pdf_literal(value: str) -> bytes:
    """Encode an ASCII/Latin-1 value as a PDF literal string.

    Parentheses and backslashes are escaped as required by PDF syntax.  The
    canonical fixtures are ASCII, while Latin-1 support keeps the helper clear
    and deterministic for common local text inputs.
    """
    try:
        encoded = value.encode("latin-1")
    except UnicodeEncodeError as error:
        raise ValueError(
            "fixture source contains characters outside PDF Latin-1 encoding"
        ) from error

    escaped = bytearray()
    for byte in encoded:
        if byte in (ord("("), ord(")"), ord("\\")):
            escaped.extend((ord("\\"), byte))
        elif byte < 32 or byte > 126:
            escaped.extend(f"\\{byte:03o}".encode("ascii"))
        else:
            escaped.append(byte)
    return bytes(escaped)


def _watermark_content(page_width: float, page_height: float) -> bytes:
    """Build a non-extractable, diagonal vector watermark content stream.

    The lettering uses simple vector glyphs instead of a PDF text operator.  It
    therefore remains visible in PDF viewers without being added to extracted
    regulatory text or parser chunks.
    """
    text_width_units = sum(4 if character == " " else 6 for character in WATERMARK_TEXT)
    angle = math.radians(WATERMARK_ANGLE_DEGREES)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    watermark_height_units = 7
    scale = min(
        3.2,
        0.9 * page_width / (cosine * text_width_units + sine * watermark_height_units),
    )
    rotated_width = scale * (cosine * text_width_units + sine * watermark_height_units)
    rotated_height = scale * (sine * text_width_units + cosine * watermark_height_units)
    translate_x = (
        page_width - rotated_width
    ) / 2 + sine * scale * watermark_height_units
    translate_y = (page_height - rotated_height) / 2

    content = bytearray()
    content.extend(f"% {WATERMARK_TEXT}\nq\n/GS1 gs\n".encode("ascii"))
    content.extend(
        f"{WATERMARK_GRAY:.3f} {WATERMARK_GRAY:.3f} {WATERMARK_GRAY:.3f} sc\n".encode(
            "ascii"
        )
    )
    content.extend(
        f"{scale * cosine:.6f} {scale * sine:.6f} "
        f"{-scale * sine:.6f} {scale * cosine:.6f} "
        f"{translate_x:.6f} {translate_y:.6f} cm\n".encode("ascii")
    )

    cursor = 0
    for character in WATERMARK_TEXT:
        if character == " ":
            cursor += 4
            continue
        glyph = WATERMARK_GLYPHS[character]
        for row, glyph_row in enumerate(glyph):
            for column, pixel in enumerate(glyph_row):
                if pixel == "1":
                    content.extend(
                        f"{cursor + column} {6 - row} 1 1 re\n".encode("ascii")
                    )
        cursor += 6

    content.extend(b"f\nQ\n")
    return bytes(content)


def build_watermark_pdf(page_width: float, page_height: float) -> bytes:
    """Build a one-page PDF overlay for an arbitrary page size."""
    page_content = _watermark_content(page_width, page_height)
    page_object = (
        "<< /Type /Page /Parent 2 0 R "
        f"/MediaBox [0 0 {page_width:g} {page_height:g}] "
        "/Resources << /ExtGState << /GS1 3 0 R >> >> "
        "/Contents 5 0 R >>"
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        f"<< /Type /ExtGState /CA {WATERMARK_ALPHA:.3f} /ca {WATERMARK_ALPHA:.3f} >>".encode(
            "ascii"
        ),
        page_object,
        f"<< /Length {len(page_content)} >>\nstream\n".encode("ascii")
        + page_content
        + b"endstream",
    ]
    return _serialize_pdf_objects(objects)


def _serialize_pdf_objects(objects: Sequence[bytes]) -> bytes:
    """Serialize an ordered list of PDF objects with a classic xref table."""
    payload = bytearray(PDF_HEADER)
    offsets = [0]
    for object_number, object_body in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{object_number} 0 obj\n".encode("ascii"))
        payload.extend(object_body)
        payload.extend(b"\nendobj\n")

    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)


def _page_content(lines: Sequence[str]) -> bytes:
    """Build one deterministic text content stream with a watermark beneath it."""
    content = bytearray(_watermark_content(PAGE_WIDTH, PAGE_HEIGHT))
    content.extend(
        f"BT\n/F1 {FONT_SIZE} Tf\n{LEADING} TL\n"
        f"{LEFT_MARGIN} {PAGE_HEIGHT - TOP_MARGIN} Td\n".encode("ascii")
    )
    for index, line in enumerate(lines):
        content.extend(b"(")
        content.extend(_escape_pdf_literal(line))
        content.extend(b") Tj\n")
        if index + 1 < len(lines):
            content.extend(b"T*\n")
    content.extend(b"ET\n")
    return bytes(content)


def _objects_for_pages(pages: Sequence[Sequence[str]]) -> list[bytes]:
    """Return PDF objects in a stable, fully explicit order."""
    page_object_numbers = [5 + page_index * 2 for page_index in range(len(pages))]
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        f"<< /Type /ExtGState /CA {WATERMARK_ALPHA:.3f} /ca {WATERMARK_ALPHA:.3f} >>".encode(
            "ascii"
        ),
    ]

    for page_number, page_lines in zip(page_object_numbers, pages):
        content_number = page_number + 1
        page_object = (
            "<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> "
            f"/ExtGState << /GS1 4 0 R >> >> "
            f"/Contents {content_number} 0 R >>"
        )
        page_content = _page_content(page_lines)
        content_object = (
            f"<< /Length {len(page_content)} >>\nstream\n".encode("ascii")
            + page_content
            + b"endstream"
        )
        objects.extend([page_object.encode("ascii"), content_object])

    return objects


def build_pdf(source_text: str) -> bytes:
    """Serialize source text and its watermark as a deterministic PDF 1.4."""
    pages = _paginate(_wrapped_lines(source_text))
    return _serialize_pdf_objects(_objects_for_pages(pages))


def _validate_mapping(mapping: Mapping[str, str]) -> None:
    """Reject any output mapping that is not exactly the three fixtures."""
    expected = set(FIXTURE_MAPPING)
    actual = set(mapping)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        unsupported = ", ".join(sorted(actual - expected)) or "none"
        raise UnsupportedFixtureMappingError(
            "unsupported fixture mapping; expected exactly the three named "
            f"outputs (missing={missing}; unsupported={unsupported})"
        )


def _read_source(source_path: Path) -> str:
    """Read and validate one canonical UTF-8 source without changing it."""
    if not source_path.is_file():
        raise MissingCanonicalSourceError(
            f"canonical source fixture not found: {source_path}"
        )
    try:
        return source_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise FixtureGenerationError(
            f"canonical source fixture is not valid UTF-8: {source_path}"
        ) from error


def generate_fixtures(
    output_directory: Path | str | None = None,
    *,
    source_directory: Path | str | None = None,
    mapping: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Generate exactly the three mapped fixture PDFs.

    Args:
        output_directory: Destination directory, defaulting to ``data/input``.
        source_directory: Canonical source directory, defaulting to the
            repository's ``data/input/fixture_sources`` directory.
        mapping: Optional mapping override for validation tests.  It must have
            exactly the same three output keys as :data:`FIXTURE_MAPPING`.

    Returns:
        The generated output paths in mapping insertion order.

    Raises:
        MissingCanonicalSourceError: If a mapped source does not exist.
        UnsupportedFixtureMappingError: If mapping contains another output.
    """
    active_mapping = mapping if mapping is not None else FIXTURE_MAPPING
    _validate_mapping(active_mapping)

    destination = (
        Path(output_directory)
        if output_directory is not None
        else DEFAULT_OUTPUT_DIRECTORY
    )
    sources = (
        Path(source_directory)
        if source_directory is not None
        else DEFAULT_SOURCE_DIRECTORY
    )
    destination.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    for output_name, source_name in active_mapping.items():
        source_path = sources / source_name
        output_path = destination / output_name
        output_path.write_bytes(build_pdf(_read_source(source_path)))
        generated.append(output_path)
    return tuple(generated)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local fixture generator command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate the three deterministic sample PDF fixtures."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="destination directory (default: data/input)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="canonical source directory (default: data/input/fixture_sources)",
    )
    args = parser.parse_args(argv)

    try:
        generated = generate_fixtures(
            output_directory=args.output_dir,
            source_directory=args.source_dir,
        )
    except FixtureGenerationError as error:
        parser.error(str(error))

    for path in generated:
        print(f"generated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
