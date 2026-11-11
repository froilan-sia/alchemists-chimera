"""
Data models for Alchemist's Chimera hybrid RAG engine.

Uses Pydantic for validation, serialization, and type safety.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from .config import QueryType


class RetrievalSource(str, Enum):
    """Source of retrieval result."""
    GRAPH = "graph"
    VECTOR = "vector"
    HYBRID = "hybrid"


class QueryRequest(BaseModel):
    """User query with metadata and configuration."""
    
    query: str = Field(..., description="The user's query text")
    query_type: Optional[QueryType] = Field(
        default=None,
        description="Query type classification (optional, will be auto-detected)"
    )
    alpha: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Graph weight parameter (0-1, optional)"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional query metadata"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "What are the capital requirements for banks under Basel III?",
                "query_type": "regulatory",
                "alpha": 0.7,
                "max_results": 10,
                "metadata": {"user_id": "user123", "session_id": "session456"}
            }
        }
    )


class RetrievalResult(BaseModel):
    """Single retrieval result with metadata and scoring."""
    
    content: str = Field(..., description="Retrieved text content")
    source: RetrievalSource = Field(..., description="Source of retrieval")
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized relevance score (0-1)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Result metadata (document ID, position, etc.)"
    )
    entity_links: Optional[List[str]] = Field(
        default=None,
        description="Linked entities from knowledge graph (if applicable)"
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Source document identifier"
    )
    chunk_index: Optional[int] = Field(
        default=None,
        description="Chunk position within document"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "content": "Basel III requires banks to maintain a minimum capital ratio of 8% of risk-weighted assets.",
                "source": "graph",
                "score": 0.92,
                "metadata": {
                    "document": "Basel_III_Framework.pdf",
                    "section": "Capital Requirements",
                    "page": 45
                },
                "entity_links": ["http://example.org/finance#BaselIII", "http://example.org/finance#CapitalRatio"],
                "document_id": "doc_123",
                "chunk_index": 3
            }
        }
    )


class HybridResponse(BaseModel):
    """Final response with answer, sources, and metadata."""
    
    answer: str = Field(..., description="Generated answer text")
    sources: List[RetrievalResult] = Field(
        ...,
        description="Retrieved sources used for answer generation"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0-1)"
    )
    query_type: QueryType = Field(..., description="Detected query type")
    processing_time: float = Field(
        ...,
        ge=0.0,
        description="Total processing time in seconds"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Response timestamp"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Under Basel III, banks must maintain a minimum capital ratio of 8% of risk-weighted assets. This includes 4.5% Common Equity Tier 1 (CET1) capital and 6% Tier 1 capital.",
                "sources": [
                    {
                        "content": "Basel III requires banks to maintain a minimum capital ratio of 8% of risk-weighted assets.",
                        "source": "graph",
                        "score": 0.92,
                        "metadata": {"document": "Basel_III_Framework.pdf", "section": "Capital Requirements"}
                    }
                ],
                "confidence": 0.88,
                "query_type": "regulatory",
                "processing_time": 2.34,
                "timestamp": "2026-11-04T14:30:00Z"
            }
        }
    )


class HealthStatus(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(default_factory=datetime.now)
    components: Dict[str, str] = Field(
        default_factory=dict,
        description="Status of individual components"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "0.1.0",
                "timestamp": "2026-11-04T14:30:00Z",
                "components": {
                    "graph_store": "healthy",
                    "vector_store": "healthy",
                    "llm": "healthy"
                }
            }
        }
    )


class ErrorResponse(BaseModel):
    """Error response for API endpoints."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Invalid query parameter",
                "detail": "Alpha parameter must be between 0 and 1",
                "timestamp": "2026-11-04T14:30:00Z"
            }
        }
    )


class DocumentUpload(BaseModel):
    """Validated metadata for a PDF document submitted for ingestion."""

    file_name: str = Field(..., min_length=1, description="Original PDF file name")
    file_content: bytes = Field(..., description="PDF bytes supplied by the caller")
    document_type: Optional[str] = Field(default=None, description="Optional document type")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional document metadata"
    )


class ExtractionStatus(BaseModel):
    """Progress snapshot for one document ingestion operation."""

    document_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    progress: float = Field(..., ge=0.0, le=1.0)
    extracted_triples: int = Field(default=0, ge=0)
    valid_triples: int = Field(default=0, ge=0)
    quarantined_triples: int = Field(default=0, ge=0)


class StagingTriple(BaseModel):
    """Serializable triple contract exposed by the human-review workflow."""

    id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    evidence_quote: str = Field(..., min_length=1)
    shacl_status: str = Field(..., min_length=1)
    validation_errors: Optional[List[str]] = None
    source_document: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)


class DocumentChunk(BaseModel):
    """Canonical document chunk contract used across ingestion boundaries."""

    chunk_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    document_name: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    chunk_index: int = Field(..., ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    """Canonical named-entity contract for extraction adapters."""

    text: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedTriple(BaseModel):
    """Canonical extracted triple contract with source evidence and anchors."""

    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    evidence_quote: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    entity_anchors: List[str] = Field(default_factory=list)


class ProvenancedTriple(BaseModel):
    """Canonical triple contract after provenance and validation enrichment."""

    triple: ExtractedTriple
    provenance_uri: str = Field(..., min_length=1)
    source_document: str = Field(..., min_length=1)
    extraction_method: str = Field(..., min_length=1)
    validation_status: str = Field(..., min_length=1)
    approval_history: List[Dict[str, Any]] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Structured validation result returned by a guardrail adapter."""

    is_valid: bool
    validation_errors: List[str] = Field(default_factory=list)
    severity: str = Field(..., min_length=1)
    suggested_fixes: Optional[List[str]] = None


class ExtractionResult(BaseModel):
    """Summary of a completed document extraction operation."""

    chunks_processed: int = Field(..., ge=0)
    triples_extracted: int = Field(..., ge=0)
    valid_triples: int = Field(..., ge=0)
    quarantined_triples: int = Field(..., ge=0)
    processing_time: float = Field(default=0.0, ge=0.0)
    errors: List[str] = Field(default_factory=list)
