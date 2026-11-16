"""Public contracts for durable asynchronous ingestion jobs."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobLifecycleStatus(str, Enum):
    """Lifecycle states persisted for an ingestion job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"

    @classmethod
    def terminal(cls) -> Set["JobLifecycleStatus"]:
        """Return statuses that require no further worker processing."""
        return {cls.COMPLETED, cls.PARTIAL, cls.FAILED, cls.CANCELED}


class JobStage(str, Enum):
    """Observable stages of upload and ingestion processing."""

    UPLOAD = "upload"
    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTING_ENTITIES = "extracting_entities"
    EXTRACTING_TRIPLES = "extracting_triples"
    VALIDATING_AND_STAGING = "validating_and_staging"
    PERSISTING_VECTORS = "persisting_vectors"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class JobModel(BaseModel):
    """Base model with safe handling of forward-compatible manifest fields."""

    model_config = ConfigDict(extra="ignore", use_enum_values=True)


class SourceMetadata(JobModel):
    """Path-independent metadata describing the accepted upload."""

    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1)
    content_sha256: str = Field(min_length=64, max_length=64)


class JobConfiguration(JobModel):
    """Configuration captured so a job can be resumed deterministically."""

    chunk_size: int = Field(default=1000, ge=100, le=5000)
    chunk_overlap: int = Field(default=200, ge=0, le=500)
    profile: str = Field(default="default", min_length=1, max_length=64)


class JobProgress(JobModel):
    """Monotonic counters exposed while a job is running."""

    fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    pages_processed: int = Field(default=0, ge=0)
    pages_total: int = Field(default=0, ge=0)
    chunks_discovered: int = Field(default=0, ge=0)
    chunks_processed: int = Field(default=0, ge=0)
    chunks_failed: int = Field(default=0, ge=0)
    triples_extracted: int = Field(default=0, ge=0)
    triples_staged: int = Field(default=0, ge=0)
    vector_chunks_persisted: int = Field(default=0, ge=0)


class JobDiagnostic(JobModel):
    """User-safe diagnostic without paths, traces, prompts, or source content."""

    code: str = Field(min_length=1, max_length=80)
    stage: JobStage
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False
    chunk_id: Optional[str] = Field(default=None, max_length=255)
    details: Dict[str, str] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def reject_sensitive_message_content(cls, value: str) -> str:
        """Reject common accidental leakage of local paths and secret payloads."""
        lowered = value.lower()
        forbidden = ("traceback", "password=", "api_key=", "/users/", "\\users\\")
        if any(token in lowered for token in forbidden):
            raise ValueError("diagnostic message contains sensitive content")
        return value


class JobResult(JobModel):
    """Serializable terminal subset of pipeline metrics."""

    total_chunks: int = Field(default=0, ge=0)
    processed_chunks: int = Field(default=0, ge=0)
    failed_chunks: int = Field(default=0, ge=0)
    total_triples: int = Field(default=0, ge=0)
    valid_triples: int = Field(default=0, ge=0)
    quarantined_triples: int = Field(default=0, ge=0)
    vector_insertions: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    document_id: Optional[str] = None
    staging_record_ids: List[str] = Field(default_factory=list)


class JobSubmissionResponse(JobModel):
    """Immediate response returned before extraction begins."""

    job_id: str
    status: JobLifecycleStatus
    status_url: str
    source: SourceMetadata
    created_at: datetime


class IngestionJobStatus(JobModel):
    """Public status snapshot returned by the submission and polling APIs."""

    job_id: str = Field(min_length=1, max_length=128)
    status: JobLifecycleStatus
    stage: JobStage
    source: SourceMetadata
    configuration: JobConfiguration = Field(default_factory=JobConfiguration)
    progress: JobProgress = Field(default_factory=JobProgress)
    diagnostics: List[JobDiagnostic] = Field(default_factory=list)
    result: Optional[JobResult] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    updated_at: datetime
    completed_at: Optional[datetime] = None
    completed_chunk_ids: List[str] = Field(default_factory=list)

    @field_validator("created_at", "started_at", "updated_at", "completed_at")
    @classmethod
    def require_timezone_aware(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Require unambiguous timestamps in persisted/public records."""
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @classmethod
    def now(cls) -> datetime:
        """Return a UTC timestamp for new records."""
        return datetime.now(timezone.utc)

    def public_dump(self) -> Dict[str, Any]:
        """Serialize only the public model fields."""
        return self.model_dump(mode="json", exclude={"completed_chunk_ids"})
