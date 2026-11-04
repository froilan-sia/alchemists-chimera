# 🎯 Project Guidelines & Architecture Standards
## For The Alchemist's Chimera - Kiroween 2026

---

## 📋 Project Overview

This document provides architectural guidelines, development patterns, and project standards for building the hybrid graph-vector RAG engine. These guidelines ensure consistent implementation and alignment with Kiroween hackathon requirements.

---

## 🏗️ Architecture Principles

### Core Principles
1. **Local-First**: All processing happens locally, no cloud dependencies
2. **Modular Design**: Components are independent and replaceable
3. **Hybrid Intelligence**: Combine deterministic (graph) and statistical (vector) approaches
4. **Kiro Integration**: Leverage Kiro's AI capabilities throughout development

### Component Architecture
```
src/
├── core/           # Core abstractions and interfaces
├── graph/          # Graph store and query engine
├── vector/         # Vector store and embedding engine
├── fusion/         # Hybrid result fusion
├── llm/           # LLM integration and generation
├── api/           # REST API layer (optional)
└── cli/           # Command-line interface
```

---

## 🔄 Data Flow Patterns

### Query Processing Pipeline
1. **Input Validation**: Sanitize and validate user query
2. **Intent Analysis**: Determine query type and retrieval strategy
3. **Parallel Retrieval**: Execute graph and vector retrieval concurrently
4. **Result Fusion**: Combine and rank results using hybrid scoring
5. **Context Assembly**: Prepare retrieved context for LLM
6. **Response Generation**: Generate final answer with citations

### Async Execution Pattern
```python
async def process_query(query: QueryRequest) -> HybridResponse:
    """Execute the full hybrid retrieval pipeline."""
    
    # Parallel retrieval
    graph_task = graph_engine.retrieve_async(query)
    vector_task = vector_engine.retrieve_async(query)
    
    graph_results, vector_results = await asyncio.gather(graph_task, vector_task)
    
    # Fusion
    fused_results = fusion_engine.fuse(graph_results, vector_results, query.alpha)
    
    # Context building
    context = context_builder.build(fused_results)
    
    # Response generation
    response = await llm_engine.generate(context, query)
    
    return HybridResponse(
        answer=response.text,
        sources=fused_results,
        confidence=response.confidence,
        query_type=query.query_type,
        processing_time=time.time() - start_time
    )
```

---

## 📊 Data Models

### Core Data Structures
```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class QueryType(str, Enum):
    ENTITY_RELATIONSHIP = "entity_relationship"
    REGULATORY = "regulatory"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"

class RetrievalSource(str, Enum):
    GRAPH = "graph"
    VECTOR = "vector"
    HYBRID = "hybrid"

class QueryRequest(BaseModel):
    """User query with metadata."""
    query: str
    query_type: Optional[QueryType] = None
    alpha: Optional[float] = None  # Graph weight (0-1)
    max_results: int = 10
    metadata: Dict[str, Any] = {}

class RetrievalResult(BaseModel):
    """Single retrieval result."""
    content: str
    source: RetrievalSource
    score: float  # Normalized 0-1
    metadata: Dict[str, Any]
    entity_links: Optional[List[str]] = None
    document_id: Optional[str] = None
    chunk_index: Optional[int] = None

class HybridResponse(BaseModel):
    """Final response with sources and metadata."""
    answer: str
    sources: List[RetrievalResult]
    confidence: float  # 0-1 confidence score
    query_type: QueryType
    processing_time: float  # seconds
    timestamp: datetime = datetime.now()
```

---

## 🔧 Configuration Management

### Environment Configuration
```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Graph store configuration
    graph_store_path: str = "./data/graph_store.ttl"
    sparql_endpoint: Optional[str] = None
    
    # Vector store configuration
    vector_store_path: str = "./data/vector_store"
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # LLM configuration
    llm_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1000
    
    # Fusion configuration
    default_alpha: Dict[QueryType, float] = {
        QueryType.ENTITY_RELATIONSHIP: 0.8,
        QueryType.REGULATORY: 0.7,
        QueryType.SEMANTIC: 0.3,
        QueryType.HYBRID: 0.5
    }
    
    # Performance configuration
    max_concurrent_queries: int = 10
    cache_ttl: int = 300  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Configuration Loading
```python
# Factory pattern for component initialization
class ComponentFactory:
    @staticmethod
    def create_graph_store(config: Settings) -> GraphStore:
        return RDFLibGraphStore(
            ontology_path=config.graph_store_path,
            sparql_endpoint=config.sparql_endpoint
        )
    
    @staticmethod
    def create_vector_store(config: Settings) -> VectorStore:
        return ChromaVectorStore(
            persist_directory=config.vector_store_path,
            embedding_model=config.embedding_model
        )
```

---

## 🎯 Performance Patterns

### Caching Strategy
```python
from functools import lru_cache
import asyncio

class HybridRetriever:
    def __init__(self):
        self._query_cache = TTLCache(maxsize=100, ttl=300)
    
    @lru_cache(maxsize=100)
    def _get_embedding(self, text: str) -> List[float]:
        """Cache embedding computations."""
        return self.embedding_model.encode(text)
    
    async def retrieve_with_cache(self, query: QueryRequest) -> HybridResponse:
        """Retrieve with query caching."""
        cache_key = self._get_cache_key(query)
        
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]
        
        response = await self._retrieve_uncached(query)
        self._query_cache[cache_key] = response
        
        return response
```

### Async Patterns
```python
# Use asyncio for I/O-bound operations
async def batch_process_queries(queries: List[QueryRequest]) -> List[HybridResponse]:
    """Process multiple queries concurrently."""
    tasks = [process_query(query) for query in queries]
    return await asyncio.gather(*tasks, return_exceptions=True)

# Use ThreadPoolExecutor for CPU-bound operations
from concurrent.futures import ThreadPoolExecutor

def compute_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Compute embeddings in parallel."""
    with ThreadPoolExecutor() as executor:
        return list(executor.map(self.embedding_model.encode, texts))
```

---

## 🧪 Testing Patterns

### Component Testing
```python
# test_hybrid_retriever.py
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_graph_store():
    store = Mock()
    store.retrieve_async = AsyncMock(return_value=[])
    return store

@pytest.fixture
def mock_vector_store():
    store = Mock()
    store.retrieve_async = AsyncMock(return_value=[])
    return store

@pytest.mark.asyncio
async def test_hybrid_retriever(mock_graph_store, mock_vector_store):
    retriever = HybridRetriever(
        graph_store=mock_graph_store,
        vector_store=mock_vector_store
    )
    
    query = QueryRequest(query="test query")
    response = await retriever.retrieve(query)
    
    assert response.answer is not None
    assert response.confidence >= 0
    assert response.confidence <= 1
```

### Integration Testing
```python
# test_integration.py
@pytest.mark.integration
class TestIntegration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.retriever = create_retriever_from_config()
    
    @pytest.mark.asyncio
    async def test_end_to_end_query(self):
        """Test complete query processing pipeline."""
        query = QueryRequest(
            query="What are the capital requirements for banks?",
            query_type=QueryType.REGULATORY
        )
        
        response = await self.retriever.retrieve(query)
        
        # Assertions
        assert response.answer is not None
        assert len(response.answer) > 0
        assert response.confidence > 0
        assert any(r.source == RetrievalSource.GRAPH for r in response.sources)
        assert any(r.source == RetrievalSource.VECTOR for r in response.sources)
```

---

## 📝 Documentation Patterns

### API Documentation
```python
from fastapi import FastAPI
from typing import List

app = FastAPI(
    title="Alchemist's Chimera API",
    description="Hybrid Graph-Vector RAG Engine",
    version="1.0.0"
)

@app.post("/query", response_model=HybridResponse)
async def process_query(query: QueryRequest) -> HybridResponse:
    """
    Process a query using hybrid graph-vector retrieval.
    
    Args:
        query: The query request with optional parameters
        
    Returns:
        Hybrid response with answer and sources
        
    Example:
        ```json
        {
            "query": "What subsidiaries does Bank of America own?",
            "query_type": "entity_relationship",
            "alpha": 0.8,
            "max_results": 10
        }
        ```
    """
    return await retriever.retrieve(query)
```

### Code Documentation
```python
class FusionEngine:
    """Orchestrates fusion of graph and vector retrieval results.
    
    This engine implements multiple fusion strategies:
    1. Weighted scoring: αS_graph + (1-α)S_vector
    2. Reciprocal Rank Fusion (RRF)
    3. Cross-encoder re-ranking
    
    Attributes:
        strategies: Available fusion strategies
        default_strategy: Strategy to use by default
    """
    
    def __init__(self, strategies: List[FusionStrategy], default_strategy: str = "weighted"):
        self.strategies = {s.name: s for s in strategies}
        self.default_strategy = default_strategy
    
    def fuse(self, graph_results: List[RetrievalResult], 
             vector_results: List[RetrievalResult], 
             alpha: float = 0.5) -> List[RetrievalResult]:
        """Fuse graph and vector results using configured strategy.
        
        Args:
            graph_results: Results from graph store
            vector_results: Results from vector store
            alpha: Graph weight parameter (0-1)
            
        Returns:
            Fused and ranked results
            
        Raises:
            FusionError: If fusion fails
        """
        strategy = self.strategies.get(self.default_strategy)
        if not strategy:
            raise FusionError(f"Strategy {self.default_strategy} not found")
        
        return strategy.fuse(graph_results, vector_results, alpha)
```

---

## 🚀 Deployment Patterns

### Docker Configuration
```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    environment:
      - GRAPH_STORE_PATH=/app/data/graph_store.ttl
      - VECTOR_STORE_PATH=/app/data/vector_store
      - LLM_MODEL=qwen2.5:3b
    restart: unless-stopped
```

---

## 🎯 Kiro Integration Patterns

### Spec-Driven Development
- Reference spec tasks in commit messages
- Update spec with implementation details
- Use Kiro for code generation from spec
- Document Kiro-assisted changes

### Steering File Usage
- Apply coding standards from steering
- Reference architectural patterns
- Use for code review guidance
- Update based on experience

### Hook Development
```python
# Example hook for validation
{
    "version": "v1",
    "hooks": [{
        "name": "Validate Ontology Changes",
        "trigger": "PostFileSave",
        "matcher": ".*\\.ttl$",
        "action": {
            "type": "command",
            "command": "python -m pyshacl ontology/finance-ontology.ttl -s ontology/shapes.ttl"
        }
    }]
}
```

---

## 📊 Monitoring & Observability

### Logging Configuration
```python
# logging_config.py
import logging
import sys

def setup_logging(level: str = "INFO"):
    """Configure structured logging."""
    
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')
        ]
    )
    
    # Set third-party loggers to WARNING
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('chromadb').setLevel(logging.WARNING)
```

### Metrics Collection
```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
QUERY_COUNT = Counter('query_total', 'Total queries processed')
QUERY_DURATION = Histogram('query_duration_seconds', 'Query processing duration')
ACTIVE_QUERIES = Gauge('active_queries', 'Number of active queries')
CACHE_HITS = Counter('cache_hits_total', 'Total cache hits')

# Instrumentation decorator
def instrument_query(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        QUERY_COUNT.inc()
        ACTIVE_QUERIES.inc()
        
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            QUERY_DURATION.observe(duration)
            ACTIVE_QUERIES.dec()
    
    return wrapper
```

---

*This guidelines document is part of the Kiroween 2026 submission for The Alchemist's Chimera.*  
*Last updated: November 4, 2026 | Version: 1.0.0*