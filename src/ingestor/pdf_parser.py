"""
PDF Parser & Chunker Module

This module provides functionality for parsing PDF documents and chunking them
into manageable text segments for downstream processing.

Responsibilities:
- PDF text extraction using pypdf
- Configurable text chunking with overlap
- Metadata tracking and unique chunk ID generation
- Error handling and progress tracking
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from pypdf import PdfReader

logger = logging.getLogger(__name__)


class PDFParserConfig(BaseModel):
    """Configuration for PDF parsing and chunking."""

    chunk_size: int = Field(
        default=1000, ge=100, le=5000, description="Size of text chunks in characters"
    )
    chunk_overlap: int = Field(
        default=200, ge=0, le=500, description="Overlap between chunks in characters"
    )
    remove_extra_whitespace: bool = Field(
        default=True, description="Remove extra whitespace from extracted text"
    )
    include_page_numbers: bool = Field(
        default=True, description="Include page numbers in chunk metadata"
    )
    max_pages: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum number of pages to process (None for all)",
    )


@dataclass
class PDFChunk:
    """Represents a chunk of text extracted from a PDF."""

    id: str
    text: str
    page_number: int
    chunk_index: int
    total_chunks: int
    metadata: Dict[str, Any]
    start_char: int
    end_char: int
    document_id: str
    document_name: str


class PDFParserError(Exception):
    """Custom exception for PDF parsing errors."""

    pass


class PDFParser:
    """Main PDF parsing and chunking class."""

    def __init__(self, config: Optional[PDFParserConfig] = None):
        """Initialize PDF parser with configuration.

        Args:
            config: Optional configuration object. Uses defaults if not provided.
        """
        self.config = config or PDFParserConfig()
        self.last_errors: List[Dict[str, Any]] = []
        self.documents_failed = 0
        logger.info("Initialized PDFParser with config: %s", self.config)

    def parse_pdf(self, pdf_path: Path) -> List[PDFChunk]:
        """Parse PDF file and return list of text chunks.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of PDFChunk objects

        Raises:
            PDFParserError: If PDF parsing fails
            FileNotFoundError: If PDF file doesn't exist
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            logger.info(f"Parsing PDF: {pdf_path}")

            # Read PDF document
            with open(pdf_path, "rb") as file:
                reader = PdfReader(file)

                # Get document metadata
                document_id = self._generate_document_id(pdf_path, reader)
                document_name = pdf_path.name
                total_pages = len(reader.pages)

                logger.info(f"Document ID: {document_id}, Total pages: {total_pages}")

                # Process pages
                chunks = []
                pages_to_process = min(
                    self.config.max_pages or total_pages, total_pages
                )

                for page_num in range(pages_to_process):
                    logger.debug(f"Processing page {page_num + 1}/{pages_to_process}")

                    try:
                        page_chunks = self._process_page(
                            reader=reader,
                            page_num=page_num,
                            document_id=document_id,
                            document_name=document_name,
                            total_pages=total_pages,
                        )
                        chunks.extend(page_chunks)

                        # Progress logging
                        if (page_num + 1) % 10 == 0 or (
                            page_num + 1
                        ) == pages_to_process:
                            logger.info(
                                f"Processed {page_num + 1}/{pages_to_process} pages, total chunks: {len(chunks)}"
                            )

                    except Exception as e:
                        self.last_errors.append({
                            "component": "pdf_parser",
                            "path": str(pdf_path),
                            "page": page_num + 1,
                            "error": str(e),
                            "severity": "WARNING",
                            "timestamp": datetime.now().isoformat(),
                        })
                        logger.warning("Skipping unreadable page %s in %s: %s", page_num + 1, pdf_path, e)
                        # Continue with next page instead of failing completely
                        continue

                logger.info(
                    f"Successfully parsed PDF. Total chunks generated: {len(chunks)}"
                )
                return chunks

        except Exception as e:
            self.documents_failed += 1
            error = {
                "component": "pdf_parser",
                "path": str(pdf_path),
                "error": str(e),
                "severity": "ERROR",
                "timestamp": datetime.now().isoformat(),
            }
            self.last_errors.append(error)
            logger.error("Failed to parse PDF %s: %s", pdf_path, e, exc_info=True)
            raise PDFParserError(
                f"Failed to parse PDF {pdf_path}: {e}. The file may be corrupted, encrypted, or unsupported."
            ) from e

    def parse_documents(self, pdf_paths: List[Path]) -> Dict[str, List[PDFChunk]]:
        """Parse multiple PDFs independently, skipping files that fail.

        A bad document must not prevent other uploaded documents from being
        ingested. Errors are retained in ``last_errors`` for UI/audit display.
        """
        results: Dict[str, List[PDFChunk]] = {}
        for pdf_path in pdf_paths:
            try:
                results[str(pdf_path)] = self.parse_pdf(Path(pdf_path))
            except (FileNotFoundError, PDFParserError) as error:
                logger.warning("Skipping unreadable PDF %s: %s", pdf_path, error)
                continue
        return results

    def health_check(self) -> Dict[str, Any]:
        """Return parser health and the most recent recoverable errors."""
        return {
            "status": "degraded" if self.last_errors else "healthy",
            "component": "pdf_parser",
            "last_error_count": len(self.last_errors),
            "documents_failed": self.documents_failed,
            "config": self.config.model_dump(),
        }

    def _process_page(
        self,
        reader: PdfReader,
        page_num: int,
        document_id: str,
        document_name: str,
        total_pages: int,
    ) -> List[PDFChunk]:
        """Process a single PDF page and generate chunks.

        Args:
            reader: PDF reader object
            page_num: Page number (0-indexed)
            document_id: Unique document identifier
            document_name: Name of the document
            total_pages: Total number of pages in document

        Returns:
            List of chunks from this page
        """
        page = reader.pages[page_num]

        # Extract text from page
        text = page.extract_text()

        # Clean text
        if self.config.remove_extra_whitespace:
            text = " ".join(text.split())

        # Skip empty pages
        if not text.strip():
            logger.warning(f"Page {page_num + 1} contains no text")
            return []

        # Chunk the text
        page_chunks = []
        page_text_length = len(text)

        if page_text_length <= self.config.chunk_size:
            # Entire page fits in one chunk
            chunk = PDFChunk(
                id=self._generate_chunk_id(document_id, page_num, 0),
                text=text,
                page_number=page_num + 1,  # Convert to 1-indexed
                chunk_index=0,
                total_chunks=1,
                metadata={
                    "document_id": document_id,
                    "document_name": document_name,
                    "total_pages": total_pages,
                    "page_text_length": page_text_length,
                    "timestamp": datetime.now().isoformat(),
                },
                start_char=0,
                end_char=page_text_length,
                document_id=document_id,
                document_name=document_name,
            )
            page_chunks.append(chunk)

        else:
            # Split page into multiple chunks
            start = 0
            chunk_index = 0

            while start < page_text_length:
                end = min(start + self.config.chunk_size, page_text_length)

                # Ensure we don't break in the middle of a word if possible
                if end < page_text_length:
                    # Try to find a word boundary
                    while end > start and text[end] not in (
                        " ",
                        "\n",
                        ".",
                        ",",
                        ";",
                        "!",
                        "?",
                    ):
                        end -= 1
                    if end <= start:  # No word boundary found, use original end
                        end = min(start + self.config.chunk_size, page_text_length)

                chunk_text = text[start:end]

                chunk = PDFChunk(
                    id=self._generate_chunk_id(document_id, page_num, chunk_index),
                    text=chunk_text,
                    page_number=page_num + 1,  # Convert to 1-indexed
                    chunk_index=chunk_index,
                    total_chunks=0,  # Will be updated later
                    metadata={
                        "document_id": document_id,
                        "document_name": document_name,
                        "total_pages": total_pages,
                        "page_text_length": page_text_length,
                        "timestamp": datetime.now().isoformat(),
                        "chunk_position": f"{start}-{end}",
                    },
                    start_char=start,
                    end_char=end,
                    document_id=document_id,
                    document_name=document_name,
                )
                page_chunks.append(chunk)

                # The final chunk reaches the end of the page. Advancing by
                # overlap would otherwise revisit the same final window.
                if end >= page_text_length:
                    break

                # Move to next chunk with overlap
                start = end - self.config.chunk_overlap
                chunk_index += 1

            # Update total chunks count for all chunks on this page
            for i, chunk in enumerate(page_chunks):
                chunk.total_chunks = len(page_chunks)
                # Update ID to reflect position in multi-chunk page if needed
                if len(page_chunks) > 1:
                    chunk.id = self._generate_chunk_id(document_id, page_num, i)

        return page_chunks

    def _generate_document_id(self, pdf_path: Path, reader: PdfReader) -> str:
        """Generate a unique document ID.

        Args:
            pdf_path: Path to PDF file
            reader: PDF reader object

        Returns:
            Unique document identifier
        """
        # Use file hash + metadata for uniqueness
        file_hash = hashlib.md5(str(pdf_path).encode()).hexdigest()[:8]
        metadata = reader.metadata or {}
        title = metadata.get("/Title", "")
        author = metadata.get("/Author", "")

        # Create a combined identifier
        identifier_parts = [
            file_hash,
            pdf_path.stem[:20],
            title[:10] if title else "",
            author[:10] if author else "",
        ]

        # Clean and join parts
        clean_parts = [
            "".join(filter(str.isalnum, part)) for part in identifier_parts if part
        ]
        document_id = (
            "-".join(clean_parts) if clean_parts else f"doc-{uuid.uuid4().hex[:8]}"
        )

        return document_id.lower()

    def _generate_chunk_id(
        self, document_id: str, page_num: int, chunk_index: int
    ) -> str:
        """Generate a unique chunk ID.

        Args:
            document_id: Document identifier
            page_num: Page number (0-indexed)
            chunk_index: Chunk index within page

        Returns:
            Unique chunk identifier
        """
        return f"{document_id}-page{page_num + 1:03d}-chunk{chunk_index:03d}"

    def parse_pdf_streaming(self, pdf_path: Path) -> Generator[PDFChunk, None, None]:
        """Parse PDF file and yield chunks as they're generated.

        This is useful for large documents to avoid memory issues.

        Args:
            pdf_path: Path to PDF file

        Yields:
            PDFChunk objects as they're generated

        Raises:
            PDFParserError: If PDF parsing fails
            FileNotFoundError: If PDF file doesn't exist
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            logger.info(f"Stream parsing PDF: {pdf_path}")

            with open(pdf_path, "rb") as file:
                reader = PdfReader(file)

                # Get document metadata
                document_id = self._generate_document_id(pdf_path, reader)
                document_name = pdf_path.name
                total_pages = len(reader.pages)

                logger.info(f"Document ID: {document_id}, Total pages: {total_pages}")

                pages_to_process = min(
                    self.config.max_pages or total_pages, total_pages
                )

                for page_num in range(pages_to_process):
                    logger.debug(
                        f"Stream processing page {page_num + 1}/{pages_to_process}"
                    )

                    try:
                        page_chunks = self._process_page(
                            reader=reader,
                            page_num=page_num,
                            document_id=document_id,
                            document_name=document_name,
                            total_pages=total_pages,
                        )

                        for chunk in page_chunks:
                            yield chunk

                        # Progress logging
                        if (page_num + 1) % 10 == 0 or (
                            page_num + 1
                        ) == pages_to_process:
                            logger.info(
                                f"Stream processed {page_num + 1}/{pages_to_process} pages"
                            )

                    except Exception as e:
                        self.last_errors.append({
                            "component": "pdf_parser",
                            "path": str(pdf_path),
                            "page": page_num + 1,
                            "error": str(e),
                            "severity": "WARNING",
                            "timestamp": datetime.now().isoformat(),
                        })
                        logger.warning("Skipping unreadable streamed page %s in %s: %s", page_num + 1, pdf_path, e)
                        continue

        except Exception as e:
            logger.error(f"Failed to stream parse PDF {pdf_path}: {e}")
            raise PDFParserError(f"Failed to stream parse PDF {pdf_path}: {e}")

    @classmethod
    def create_default_parser(cls) -> "PDFParser":
        """Create a parser with default configuration.

        Returns:
            PDFParser instance with default config
        """
        return cls(PDFParserConfig())


def main():
    """Example usage and testing of PDF parser."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <pdf_file>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)

    try:
        # Create parser
        parser = PDFParser.create_default_parser()

        # Parse PDF
        print(f"Parsing PDF: {pdf_path}")
        chunks = parser.parse_pdf(pdf_path)

        # Display results
        print(f"\nParsing complete!")
        print(f"Total chunks generated: {len(chunks)}")

        if chunks:
            print(f"\nFirst chunk preview:")
            first_chunk = chunks[0]
            print(f"ID: {first_chunk.id}")
            print(f"Page: {first_chunk.page_number}")
            print(f"Text (first 200 chars): {first_chunk.text[:200]}...")

            print(f"\nLast chunk preview:")
            last_chunk = chunks[-1]
            print(f"ID: {last_chunk.id}")
            print(f"Page: {last_chunk.page_number}")
            print(f"Text (first 200 chars): {last_chunk.text[:200]}...")

        # Demonstrate streaming
        print(f"\nStreaming demonstration:")
        stream_chunks = []
        for chunk in parser.parse_pdf_streaming(pdf_path):
            stream_chunks.append(chunk)
            if len(stream_chunks) <= 3:
                print(f"  Streamed chunk: {chunk.id}")

        print(f"Total streamed chunks: {len(stream_chunks)}")

    except Exception as e:
        print(f"Error parsing PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
