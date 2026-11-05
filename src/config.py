"""
Configuration management for Alchemist's Chimera.

Uses pydantic-settings for environment-aware configuration with
sensible defaults for local development.
"""

from typing import Dict, Optional
from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import Field


class QueryType(str, Enum):
    """Query type classification."""
    ENTITY_RELATIONSHIP = "entity_relationship"
    REGULATORY = "regulatory"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class Settings(BaseSettings):
    """Application settings with environment-aware defaults."""
    
    # Environment
    environment: str = Field(default="development", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Graph store configuration
    graph_store_path: str = Field(
        default="./ontology/finance-ontology.ttl",
        description="Path to RDF ontology file"
    )
    sparql_endpoint: Optional[str] = Field(
        default=None,
        description="External SPARQL endpoint (optional)"
    )
    
    # Vector store configuration
    vector_store_path: str = Field(
        default="./data/vector_store",
        description="ChromaDB persistence directory"
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model for embeddings"
    )
    chunk_size: int = Field(
        default=1000,
        description="Document chunk size for vector store"
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between document chunks"
    )
    
    # LLM configuration
    llm_model: str = Field(
        default="qwen2.5:3b",
        description="Ollama model for response generation"
    )
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature (0=deterministic, 2=creative)"
    )
    llm_max_tokens: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum tokens for LLM response"
    )
    
    # Fusion configuration
    default_alpha: Dict[QueryType, float] = Field(
        default={
            QueryType.ENTITY_RELATIONSHIP: 0.8,
            QueryType.REGULATORY: 0.7,
            QueryType.SEMANTIC: 0.3,
            QueryType.HYBRID: 0.5,
        },
        description="Default graph weights by query type"
    )
    
    # Performance configuration
    max_concurrent_queries: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent queries"
    )
    cache_ttl: int = Field(
        default=300,
        description="Cache time-to-live in seconds"
    )
    
    # API configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=1, description="API worker processes")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings