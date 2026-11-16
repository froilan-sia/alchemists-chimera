"""Bounded, local spooling and validation for uploaded PDF streams."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, BinaryIO, Optional
from uuid import uuid4


class UploadValidationError(ValueError):
    """Base class for upload rejection before a job is queued."""

    code = "UPLOAD_INVALID"


class UploadEmptyError(UploadValidationError):
    """The upload contained no bytes."""

    code = "UPLOAD_EMPTY"


class UploadTooLargeError(UploadValidationError):
    """The upload exceeded the configured byte limit."""

    code = "UPLOAD_TOO_LARGE"


class UploadNotPdfError(UploadValidationError):
    """The filename or file signature did not identify a PDF."""

    code = "UPLOAD_NOT_PDF"


class UploadIoError(UploadValidationError):
    """The local spool could not be written safely."""

    code = "UPLOAD_IO_FAILED"


@dataclass(frozen=True)
class UploadedSource:
    """Committed source metadata and its private local path."""

    path: Path
    file_name: str
    size_bytes: int
    content_sha256: str


class UploadedPdfStore:
    """Copy uploads in bounded blocks into job-scoped seekable source files."""

    def __init__(self, root: Path = Path("data/uploads/jobs"), max_bytes: int = 25_000_000,
                 block_size: int = 64 * 1024) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes
        self.block_size = block_size

    @staticmethod
    def safe_file_name(name: str) -> str:
        """Return a safe display filename without trusting path components."""
        basename = Path(str(name or "")).name
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(basename).stem).strip("._") or "document"
        return f"{stem}.pdf"

    def spool(self, uploaded: Any, job_id: str) -> UploadedSource:
        """Validate and atomically spool an upload for a newly accepted job."""
        original_name = str(getattr(uploaded, "filename", None) or getattr(uploaded, "name", ""))
        if Path(original_name).suffix.lower() != ".pdf":
            raise UploadNotPdfError("Only PDF files can be uploaded.")
        file_name = self.safe_file_name(original_name)
        job_dir = self.root / job_id
        temporary_path = job_dir / f".source-{uuid4().hex}.tmp"
        source_path = job_dir / "source.pdf"
        digest = hashlib.sha256()
        size = 0
        first_bytes = b""

        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            with temporary_path.open("wb") as destination:
                for block in self._blocks(uploaded):
                    if not block:
                        break
                    if not first_bytes:
                        first_bytes = block[:5]
                    size += len(block)
                    if size > self.max_bytes:
                        raise UploadTooLargeError(
                            f"Upload exceeds the {self.max_bytes} byte limit."
                        )
                    digest.update(block)
                    destination.write(block)
                destination.flush()
                os.fsync(destination.fileno())
            if size == 0:
                raise UploadEmptyError("The uploaded PDF is empty.")
            if first_bytes != b"%PDF-":
                raise UploadNotPdfError("The upload does not contain a PDF signature.")
            temporary_path.replace(source_path)
            return UploadedSource(source_path, file_name, size, digest.hexdigest())
        except UploadValidationError:
            temporary_path.unlink(missing_ok=True)
            raise
        except (OSError, IOError) as error:
            temporary_path.unlink(missing_ok=True)
            raise UploadIoError("The uploaded PDF could not be stored locally.") from error

    def remove(self, job_id: str) -> None:
        """Remove a rejected or explicitly expired job source."""
        job_dir = self.root / job_id
        try:
            for path in job_dir.glob(".source-*.tmp"):
                path.unlink(missing_ok=True)
            (job_dir / "source.pdf").unlink(missing_ok=True)
            job_dir.rmdir()
        except OSError:
            return

    def _blocks(self, uploaded: Any):
        """Yield bounded blocks from common FastAPI and Streamlit upload APIs."""
        stream: Optional[BinaryIO] = getattr(uploaded, "file", None)
        if stream is None and hasattr(uploaded, "read"):
            stream = uploaded
        if stream is not None:
            while True:
                block = stream.read(self.block_size)
                if not block:
                    return
                yield bytes(block)
            return
        buffer = getattr(uploaded, "getbuffer", None)
        if callable(buffer):
            view = buffer()
            for start in range(0, len(view), self.block_size):
                yield bytes(view[start:start + self.block_size])
            return
        # Legacy direct helpers may expose only getvalue(). The API path never
        # uses this fallback because FastAPI UploadFile provides a file stream.
        getvalue = getattr(uploaded, "getvalue", None)
        if callable(getvalue):
            value = getvalue()
            for start in range(0, len(value), self.block_size):
                yield bytes(value[start:start + self.block_size])
            return
        raise UploadIoError("Upload stream does not support bounded reads.")
