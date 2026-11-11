# Ingestion Pipeline Orchestrator

The Ingestion Pipeline Orchestrator is the core component of The Alchemist's Chimera that processes PDF documents, extracts structured knowledge (RDF triples), and prepares them for hybrid graph-vector retrieval.

## 🎯 Features

### 1. **Sequential Chunk Processing**
- ✅ No parallelization for Hugging Face Spaces compatibility
- ✅ Stable memory and CPU usage
- ✅ Small delays between chunks for resource stability

### 2. **Complete Workflow Coordination**
- ✅ PDF Parser: Extracts text chunks from PDFs
- ✅ Entity Extractor: Identifies named entities using spaCy
- ✅ Triple Extractor: Extracts RDF triples using Ollama LLM
- ✅ Provenance Manager: Creates RDF provenance with URI normalization
- ✅ SHACL Validator: Validates triples against shape constraints
- ✅ Staging Manager: HITL workflow for human review
- ✅ Vector Store: Immediate insertion for hybrid retrieval

### 3. **Evidence Grounding Verification**
- ✅ Verbatim substring checks for evidence quotes
- ✅ Case-insensitive matching against original text
- ✅ Minimum evidence length validation

### 4. **Error Handling & Recovery**
- ✅ Individual chunk failures don't stop entire pipeline
- ✅ Comprehensive progress tracking with `PipelineMetrics`
- ✅ Detailed logging at all stages
- ✅ Status reporting with `PipelineStatus`

## 🚀 Quick Start

### Basic Usage

```python
from ingestor.pipeline import create_default_pipeline

# Create pipeline
pipeline = create_default_pipeline()

# Process a PDF
metrics = pipeline.process_pdf("data/input/sample.pdf")

# View results
print(f"Processed {metrics.processed_chunks} chunks")
print(f"Extracted {metrics.total_triples} triples")
print(f"Valid triples: {metrics.valid_triples}")
print(f"Quarantined triples: {metrics.quarantined_triples}")
```

### Custom Configuration

```python
from ingestor.pipeline import IngestionPipeline

config = {
    "chunk_size": 800,
    "chunk_overlap": 100,
    "entity_types": ["ORG", "LAW", "MONEY"],
    "model_name": "qwen2.5:3b",
    "confidence_threshold": 0.6,
    "base_uri": "http://alchemists-chimera.org/finance/",
}

pipeline = IngestionPipeline(config)
```

### HITL Workflow

```python
# Get staging statistics
stats = pipeline.staging_manager.get_stats()
print(f"Pending review: {stats['pending_review']}")

# Get records needing human review
pending = pipeline.staging_manager.get_pending_review()
for record in pending:
    print(f"Triple: {record.triple.subject} {record.triple.predicate} {record.triple.object}")
    print(f"Status: {record.validation_status.value}")
    print(f"Confidence: {record.triple.confidence:.2f}")

# Mark as reviewed (example)
# pipeline.staging_manager.mark_as_reviewed(record_id, "reviewer_name", ValidationStatus.VALID)
```

## 📊 Pipeline Metrics

The pipeline tracks comprehensive metrics:

```python
metrics = pipeline.process_pdf("document.pdf")

# Access metrics
print(f"Duration: {metrics.duration_seconds:.2f}s")
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"Validation rate: {metrics.validation_rate:.1%}")
print(f"Vector insertions: {metrics.vector_insertions}")

# Get full status report
status = pipeline.get_status()
print(f"Pipeline status: {status['pipeline_status']}")
print(f"Staging records: {status['staging']['total_records']}")
```

## 🔧 Components

### 1. **PDF Parser** (`pdf_parser.py`)
- Extracts text from PDFs with configurable chunking
- Preserves metadata and page numbers
- Generates unique document and chunk IDs

### 2. **Entity Extractor** (`entity_extractor.py`)
- Uses spaCy NLP for named entity recognition
- Focuses on regulatory entities (ORG, PERSON, LAW, MONEY, GPE)
- Confidence scoring and deduplication

### 3. **Triple Extractor** (`triple_extractor.py`)
- Uses Ollama LLM for RDF triple extraction
- Sequential processing for resource constraints
- Evidence extraction and confidence scoring

### 4. **Provenance Manager** (`provenance_manager.py`)
- Creates RDF provenance with proper URI normalization
- Ensures RDFLib and pyshacl compatibility
- Serializes to Turtle format with namespace binding

### 5. **SHACL Validator** (`shacl_validator.py`)
- Validates triples against SHACL shape constraints
- Basic validation fallback if pyshacl not available
- Classification (valid/quarantined/invalid)

### 6. **Staging Manager** (in `pipeline.py`)
- Manages HITL workflow for human review
- Persists staging records to disk
- Tracks review status and decisions

### 7. **Vector Store Integration**
- Inserts chunks into ChromaDB vector store
- Enables immediate hybrid retrieval
- Tracks metadata for provenance

## 🛡️ Hugging Face Spaces Safeguards

### Safeguard 4: Sequential Processing
```python
# Implementation in process_pdf() method
for i, chunk in enumerate(chunks, 1):
    self._process_chunk(chunk)  # Sequential, not parallel
    
    # Small delay for resource stability
    if i < len(chunks):
        time.sleep(0.1)
```

### Resource Management
- No parallel processing to avoid CPU/Memory spikes
- Configurable chunk sizes for memory control
- Exponential backoff for API calls
- Graceful error recovery

## 📝 Validation Pipeline

1. **Basic Validation**: Required fields, confidence ranges
2. **Evidence Grounding**: Verbatim substring checks
3. **SHACL Validation**: Shape constraint validation
4. **Classification**: Valid/Quarantined/Invalid
5. **Staging**: HITL workflow for quarantined triples

## 🧪 Testing

Run the test suite:
```bash
python test_pipeline.py
```

Or test individual components:
```python
python -m ingestor.pipeline  # Run pipeline module directly
python -m ingestor.shacl_validator  # Test SHACL validator
```

## 📈 Monitoring

### Status Monitoring
```python
status = pipeline.get_status()
print(f"Status: {status['pipeline_status']}")
print(f"Metrics: {status['metrics']}")
print(f"Staging: {status['staging']}")
print(f"Vector Store: {status['vector_store']}")
```

### Logging
The pipeline uses structured logging:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

## 🔄 Pipeline Reset

Reset pipeline state for new processing:
```python
pipeline.reset()
status = pipeline.get_status()
print(f"Reset status: {status['pipeline_status']}")  # Should be "pending"
```

## 📚 Examples

See comprehensive examples in:
```
examples/pipeline_usage.py
```

## 🎯 Compliance with Project Guidelines

- ✅ PEP 8 standards and type hints
- ✅ Pydantic models for configuration
- ✅ Proper error handling and logging
- ✅ Single responsibility principle
- ✅ Integration with existing architecture
- ✅ Kiro workflow patterns (spec-driven development)

## 🤝 Integration Points

- Uses existing `VectorStore` from `vector_store.py`
- Integrates with project `settings` from `config.py`
- Compatible with data models from `models.py`
- Follows project coding standards

---

**Implementation**: November 2026  
**Project**: The Alchemist's Chimera - Kiroween 2026  
**Developer**: Kiro AI Assistant
