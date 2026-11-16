"""Generate deterministic PDF fixtures from canonical local source text.

The generator intentionally has no third-party or network dependencies.  Its
only outputs are the three named regulatory fixture PDFs, and its canonical
source files are never modified.
"""

from __future__ import annotations

import argparse
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
FONT_OBJECT_NUMBER = 3
PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


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


def _page_content(lines: Sequence[str]) -> bytes:
    """Build one deterministic text content stream."""
    content = bytearray(
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
    page_object_numbers = [4 + page_index * 2 for page_index in range(len(pages))]
    content_object_numbers = [number + 1 for number in page_object_numbers]
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

    for page_number, page_lines in zip(page_object_numbers, pages):
        content_number = page_number + 1
        page_object = (
            "<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {FONT_OBJECT_NUMBER} 0 R >> >> "
            f"/Contents {content_number} 0 R >>"
        )
        page_content = _page_content(page_lines)
        content_object = (
            f"<< /Length {len(page_content)} >>\nstream\n".encode("ascii")
            + page_content
            + b"endstream"
        )
        # Page and stream objects alternate in page order.
        objects.extend([page_object.encode("ascii"), content_object])

    return objects


def build_pdf(source_text: str) -> bytes:
    """Serialize source text as a deterministic, self-contained PDF 1.4."""
    pages = _paginate(_wrapped_lines(source_text))
    objects = _objects_for_pages(pages)

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

    destination = Path(output_directory) if output_directory is not None else DEFAULT_OUTPUT_DIRECTORY
    sources = Path(source_directory) if source_directory is not None else DEFAULT_SOURCE_DIRECTORY
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
