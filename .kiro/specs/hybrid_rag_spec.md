# 🎯 Hybrid Graph-Vector RAG Engine: Technical Specification
## 🎃 Built for Kiroween Hackathon 2026

## 📋 Executive Summary

**The Alchemist's Chimera** is a local hybrid RAG engine that fuses deterministic knowledge graphs with statistical vector search to overcome the limitations of traditional RAG systems. This specification outlines the architecture, components, and implementation plan for a production-ready hybrid retrieval system optimized for Apple Silicon M-series Macs.

**Kiroween Hackathon Compliance**: This project is developed specifically for the Kiroween 2026 hackathon (October 30 - December 4, 2026) and demonstrates comprehensive utilization of Kiro's AI-powered development capabilities including spec-driven development, steering files, hooks, and agentic workflows.

**Target Use Case**: Financial document analysis, regulatory compliance queries, and enterprise knowledge management requiring both precise entity relationships and semantic context understanding.

## 🎃 Kiroween Hackathon Requirements Compliance

### Submission Requirements
- ✅ **New Project**: Built during submission period (Oct 30 - Dec 4, 2026)
- ✅ **Kiro Integration**: Comprehensive use of Kiro features documented
- ✅ **Video Demo**: 2-minute demonstration video included
- ✅ **Team Size**: Individual submission or team of up to 3 members
- ✅ **Original Work**: All code developed for this hackathon

### Judging Criteria Alignment
| Criteria | Weight | Our Approach |
|----------|--------|--------------|
| **Potential Value** | 33% | Solves real enterprise RAG limitations, local-first architecture |
| **Implementation of Kiro** | 33% | Full Kiro workflow: specs → steering → hooks → implementation |
| **Creativity** | 33% | Novel fusion of graph+vector, Frankenstein-inspired architecture |

### Kiro Feature Utilization
1. **Spec-Driven Development**: This document as living specification
2. **Steering Files**: Coding standards and project guidelines
3. **Agent Hooks**: Automated validation and testing
4. **AI-Powered Development**: Kiro as co-developer throughout
5. **MCP Integration**: Optional external tool integration

## 🏗️ System Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    User Query Input                          │
└───────────────────────┬─────────────────────────────────────┘
                        │
           ┌────────────▼─────────────┐
           │   Intent Classifier       │
           │  (Query Type Detection)   │
           └────────────┬─────────────┘
                        │
           ┌────────────▼─────────────┐
           │   Dual-Branch Router      │
           │  (Graph vs Vector Bias)   │
           └────────────┬─────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼───────┐ ┌─────▼──────┐ ┌──────▼───────┐
│  Graph Engine │ │  Fusion    │ │ Vector Engine│
│  (RDFLib)     │ │  Orchestrator│ │ (ChromaDB)  │
│  • SPARQL     │ │  • Weighted │ │ • Embeddings │
│  • Inference  │ │  • RRF      │ │ • Semantic   │
│  • SHACL      │ │  • Cross-   │ │ • Similarity │
│               │ │  Encoder    │ │              │
└───────┬───────┘ └─────┬──────┘ └──────┬───────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
           ┌────────────▼─────────────┐
           │   Result Fusion Layer     │
           │  S_hybrid = αS_graph +    │
           │       (1-α)S_vector       │
           └────────────┬─────────────┘
                        │
           ┌────────────▼─────────────┐
           │   LLM Context Builder     │
           │  • Prompt Engineering     │
           │  • Context Assembly       │
           └────────────┬─────────────┘
                        │
           ┌────────────▼─────────────┐
           │   Response Generation     │
           │  (Ollama/Qwen2.5)        │
           └──────────────────────────┘
```

### Mathematical Foundation

The hybrid scoring function:

$$S_{\text{hybrid}} = \alpha(t) \cdot S_{\text{graph}} + (1 - \alpha(t)) \cdot S_{\text{vector}}$$

Where:
- $S_{\text{graph}}$: Normalized graph relevance score (0-1)
- $S_{\text{vector}}$: Normalized vector similarity score (0-1)
- $\alpha(t)$: Dynamic weighting function based on query type $t$

### Query Type Classification

| Query Type | α (Graph Weight) | Characteristics | Example |
|------------|------------------|-----------------|---------|
| **Entity-Relationship** | 0.8 | Focus on specific entities, hierarchies, regulations | "What subsidiaries does Bank of America own?" |
| **Regulatory** | 0.7 | Compliance, rules, legal frameworks | "What are the Basel III capital requirements?" |
| **Semantic** | 0.3 | Conceptual, abstract, narrative context | "Explain the impact of quantitative easing on inflation" |
| **Hybrid** | 0.5 | Mixed entity and conceptual queries | "How did Apple's stock perform after their last earnings call?" |

## 📦 Component Specifications

### 1. Intent Classifier (`src/intent_classifier.py`)
- **Purpose**: Detect query type for routing decisions
- **Input**: Natural language query
- **Output**: Query type classification + confidence score
- **Implementation**: Rule-based + lightweight ML classifier
- **Key Features**:
  - Named Entity Recognition (NER) for entity detection
  - Keyword matching for regulatory terminology
  - Semantic similarity to query templates

### 2. Dual-Branch Router (`src/router.py`)
- **Purpose**: Route queries to appropriate retrieval engines
- **Input**: Query + intent classification
- **Output**: Routing plan with engine weights
- **Implementation**: Weighted routing based on α parameter
- **Key Features**:
  - Configurable routing thresholds
  - Fallback mechanisms
  - Performance monitoring

### 3. Graph Store Engine (`src/graph_store.py`)
- **Purpose**: Execute SPARQL queries and graph traversals
- **Technology Stack**: RDFLib, existing finance ontology
- **Key Features**:
  - Integration with finance-ontology-rag ontology
  - SPARQL 1.1 support
  - Inference engine integration (HermiT/Pellet)
  - SHACL validation hooks
  - Subgraph extraction for context building

### 4. Vector Store Engine (`src/vector_store.py`)
- **Purpose**: Semantic similarity search and embedding retrieval
- **Technology Stack**: ChromaDB, sentence-transformers
- **Key Features**:
  - Local embedding models (all-MiniLM-L6-v2)
  - Document chunking strategies
  - Metadata filtering
  - Reciprocal Rank Fusion (RRF) support

### 5. Fusion Orchestrator (`src/fusion.py`)
- **Purpose**: Combine and rank results from both engines
- **Input**: Ranked lists from graph and vector engines
- **Output**: Unified ranked list with hybrid scores
- **Implementation**: Weighted scoring + RRF
- **Key Features**:
  - Configurable fusion strategies
  - Cross-encoder re-ranking option
  - Deduplication
  - Confidence calibration

### 6. LLM Context Builder (`src/context_builder.py`)
- **Purpose**: Assemble retrieval results into LLM context
- **Input**: Ranked retrieval results
- **Output**: Structured prompt with citations
- **Key Features**:
  - Citation tracking
  - Context window optimization
  - Prompt templating
  - Relevance filtering

### 7. Response Generator (`src/response_generator.py`)
- **Purpose**: Generate final answers using local LLM
- **Technology Stack**: Ollama, Qwen2.5:3b
- **Key Features**:
  - Streaming responses
  - Citation inclusion
  - Confidence scoring
  - Response validation

## 🛠️ Kiro Development Workflow

### Spec-Driven Development
1. **This Document**: Living specification updated throughout development
2. **Task Breakdown**: Sequenced implementation tasks below
3. **Progress Tracking**: GitHub Issues linked to spec sections

### Steering Files (`/.kiro/steering/`)
1. **coding_standards.md**: PEP 8, type hints, documentation standards
2. **project_guidelines.md**: Architecture patterns, testing requirements
3. **kiro_workflow.md**: Kiro-specific development procedures

### Agent Hooks (`/.kiro/hooks/`)
1. **validate_ontology.sh**: SHACL validation on ontology changes
2. **run_tests.sh**: Automated test execution on file save
3. **lint_on_save.sh**: Code quality checks before commit

### AI-Powered Development
1. **Kiro as Co-developer**: Real-time code generation and review
2. **Context Awareness**: Kiro understands project structure and patterns
3. **Error Diagnosis**: AI-assisted debugging and optimization

## 🔧 Technical Requirements

### Dependencies
```python
# Core Dependencies (from requirements.txt)
rdflib>=7.0.0          # Graph operations
chromadb>=0.4.20       # Vector database
pydantic>=2.5.0        # Data validation
fastapi>=0.110.0       # API layer (optional)
uvicorn>=0.28.0        # ASGI server (optional)
numpy>=1.26.0          # Numerical operations

# Additional Dependencies Needed
sentence-transformers>=2.2.0  # Embeddings
spacy>=3.7.0                  # NLP/NER
scikit-learn>=1.3.0           # ML classifiers
ollama>=0.1.0                 # Local LLM
pyshacl>=0.21.0               # SHACL validation
```

### Data Models
```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class QueryRequest(BaseModel):
    query: str
    query_type: Optional[str] = None
    alpha: Optional[float] = None
    max_results: int = 10

class RetrievalResult(BaseModel):
    content: str
    source: str  # "graph" or "vector"
    score: float
    metadata: Dict[str, Any]
    entity_links: Optional[List[str]] = None

class HybridResponse(BaseModel):
    answer: str
    sources: List[RetrievalResult]
    confidence: float
    query_type: str
    processing_time: float
```

## 📊 Performance Metrics

### Retrieval Metrics
- **Precision@K**: Top-K retrieval accuracy
- **Recall@K**: Coverage of relevant documents
- **MRR (Mean Reciprocal Rank)**: Ranking quality
- **NDCG@K**: Normalized Discounted Cumulative Gain

### Fusion Metrics
- **Fusion Gain**: Improvement over single-engine retrieval
- **α Effectiveness**: Weighting parameter optimization
- **Latency**: End-to-end processing time
- **Accuracy**: Final answer correctness

### Quality Metrics
- **Hallucination Rate**: False information generation
- **Citation Accuracy**: Source attribution correctness
- **Context Relevance**: Retrieved context usefulness
- **Response Coherence**: Answer quality and fluency

## 🚀 Implementation Roadmap

### Phase 1: Foundation & Kiro Setup (Week 1)
**Goal**: Establish core infrastructure with Kiro workflow integration

#### Task List:
1. **Kiro Project Configuration**
   - [ ] Initialize Kiro workspace with proper structure
   - [ ] Create steering files for coding standards
   - [ ] Set up agent hooks for automated validation
   - [ ] Configure Kiro development environment
   - [ ] Document Kiro workflow in README

2. **Project Setup & Environment**
   - [ ] Initialize virtual environment
   - [ ] Install and configure dependencies
   - [ ] Set up development environment
   - [ ] Create project structure documentation
   - [ ] Implement Kiro-aware dependency management

3. **Graph Engine Integration**
   - [ ] Integrate finance ontology from finance-ontology-rag
   - [ ] Implement RDFLib graph store interface
   - [ ] Create SPARQL query executor
   - [ ] Add inference engine support
   - [ ] Implement SHACL validation hooks

4. **Vector Engine Setup**
   - [ ] Configure ChromaDB with local persistence
   - [ ] Implement embedding model integration
   - [ ] Create document ingestion pipeline
   - [ ] Design chunking strategies
   - [ ] Implement metadata indexing

### Phase 2: Intelligence & Kiro Automation (Week 2-3)
**Goal**: Add intent classification and fusion logic with Kiro automation

#### Task List:
5. **Intent Classifier Implementation**
   - [ ] Design rule-based classifier
   - [ ] Implement NER for entity detection
   - [ ] Create keyword database for financial terms
   - [ ] Add ML-based classifier (optional enhancement)
   - [ ] Implement confidence scoring

6. **Router Implementation**
   - [ ] Create dual-branch routing logic
   - [ ] Implement dynamic α parameter calculation
   - [ ] Add fallback mechanisms
   - [ ] Create routing performance monitor
   - [ ] Implement configuration management

7. **Fusion Engine Development**
   - [ ] Implement weighted scoring algorithm
   - [ ] Add Reciprocal Rank Fusion (RRF)
   - [ ] Create cross-encoder re-ranking
   - [ ] Implement deduplication logic
   - [ ] Add score normalization

8. **Kiro Automation Features**
   - [ ] Create hook for automated testing
   - [ ] Implement steering for code quality
   - [ ] Add spec validation hooks
   - [ ] Create Kiro workflow documentation
   - [ ] Implement progress tracking

### Phase 3: Enhancement & Kiro Optimization (Week 4)
**Goal**: Add LLM integration and Kiro-powered optimization

#### Task List:
9. **LLM Integration**
   - [ ] Integrate Ollama API
   - [ ] Configure Qwen2.5:3b model
   - [ ] Implement streaming response handling
   - [ ] Add response validation
   - [ ] Create error handling for LLM failures

10. **Performance Optimization with Kiro**
    - [ ] Implement caching layer with Kiro guidance
    - [ ] Add concurrent execution for dual retrieval
    - [ ] Optimize embedding generation
    - [ ] Implement batch processing
    - [ ] Add memory management

11. **Quality Assurance**
    - [ ] Create comprehensive test suite
    - [ ] Implement integration tests
    - [ ] Add performance benchmarking
    - [ ] Create validation datasets
    - [ ] Implement automated testing pipeline

12. **Kiro Development Showcase**
    - [ ] Document Kiro feature usage
    - [ ] Create video demo showcasing Kiro workflow
    - [ ] Prepare submission materials
    - [ ] Optimize for judging criteria
    - [ ] Final Kiro integration review

### Phase 4: Productionization & Submission (Week 5)
**Goal**: Prepare for deployment and Kiroween submission

#### Task List:
13. **API Layer Development**
    - [ ] Create FastAPI application
    - [ ] Implement REST endpoints
    - [ ] Add authentication/authorization
    - [ ] Create API documentation
    - [ ] Implement rate limiting

14. **Deployment Configuration**
    - [ ] Create Docker configuration
    - [ ] Implement environment management
    - [ ] Add configuration validation
    - [ ] Create deployment scripts
    - [ ] Implement health monitoring

15. **Kiroween Submission Preparation**
    - [ ] Create 2-minute demo video
    - [ ] Prepare Devpost submission
    - [ ] Document Kiro implementation details
    - [ ] Create judging criteria alignment document
    - [ ] Final submission review

16. **Documentation & Examples**
    - [ ] Create comprehensive documentation
    - [ ] Add usage examples
    - [ ] Create API client examples
    - [ ] Add troubleshooting guide
    - [ ] Create Kiro workflow showcase

## 🧪 Testing Strategy

### Unit Tests
- Individual component testing
- Mock dependencies for isolation
- Edge case coverage

### Integration Tests
- Component interaction testing
- End-to-end query flow
- Error handling scenarios

### Performance Tests
- Latency measurements
- Memory usage profiling
- Concurrent request handling

### Kiro Workflow Tests
- Hook execution validation
- Steering file effectiveness
- Spec-driven development workflow
- AI-assisted development patterns

## 🔒 Security Considerations

1. **Data Privacy**: All processing local, no data leaves the system
2. **Input Validation**: Sanitize all user inputs
3. **Rate Limiting**: Prevent abuse of LLM resources
4. **Resource Isolation**: Sandbox execution environments
5. **Audit Logging**: Track all queries and responses

## 📈 Success Criteria

### Kiroween Judging Alignment
| Criteria | Target Score | Implementation |
|----------|-------------|----------------|
| **Potential Value** | 90%+ | Solves real RAG limitations, enterprise-ready |
| **Kiro Implementation** | 95%+ | Full spec→steering→hooks→code workflow |
| **Creativity** | 90%+ | Novel hybrid architecture, Frankenstein theme |

### Technical Milestones
- [ ] Basic dual-engine retrieval operational
- [ ] Intent classification with >80% accuracy
- [ ] Fusion layer producing combined results
- [ ] Local LLM generating coherent responses
- [ ] End-to-end query processing <5 seconds
- [ ] Comprehensive Kiro workflow documentation
- [ ] Demo video showcasing Kiro features

## 🔗 Integration Points

### Existing Repository Integration
1. **Finance Ontology**: Import and extend from `finance-ontology-rag/ontology/finance-ontology.ttl`
2. **SHACL Validation**: Integrate validation hooks from existing pipeline
3. **Entity Extraction**: Leverage LLM extraction patterns from Article 4
4. **Dual-Branch Patterns**: Adapt fusion logic from `rag_fusion.py`

### Kiro Integration
1. **Spec-Driven Workflow**: This document as living specification
2. **Steering Automation**: Coding standards and quality gates
3. **Hook Ecosystem**: Automated testing and validation
4. **AI Collaboration**: Kiro as development partner throughout

## 🚨 Risk Mitigation

| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| LLM Hallucinations | Medium | High | Source citation, confidence scoring, validation layers |
| Performance Issues | High | Medium | Caching, concurrent execution, optimization profiling |
| Ontology Complexity | Medium | Medium | Incremental expansion, validation tools, documentation |
| Local Resource Limits | High | Medium | Resource monitoring, batch processing, optimization |
| Kiro Integration Challenges | Low | Medium | Clear documentation, testing, gradual implementation |

## 📚 References & Resources

1. **Kiroween Hackathon**: https://kiroween.devpost.com/
2. **Existing Codebase**: https://github.com/froilan-sia/finance-ontology-rag
3. **Project Repository**: https://github.com/froilan-sia/alchemists-chimera
4. **RDFLib Documentation**: https://rdflib.readthedocs.io/
5. **ChromaDB Documentation**: https://docs.trychroma.com/
6. **Ollama Documentation**: https://github.com/ollama/ollama
7. **Kiro Documentation**: https://kiro.dev/docs

## 👥 Team Roles & Responsibilities

| Role | Responsibilities | Skills Required |
|------|-----------------|----------------|
| **Core Developer** | Implementation, testing, optimization | Python, RDF, Vector DBs, ML |
| **Ontology Specialist** | Graph design, validation, expansion | OWL, SPARQL, SHACL, Finance Domain |
| **Kiro Workflow Expert** | Kiro integration, documentation | Kiro, Spec-driven development, Automation |
| **Submission Coordinator** | Devpost submission, demo video | Documentation, Presentation, Video editing |

## 📅 Timeline & Milestones

| Milestone | Target Date | Deliverables | Kiro Focus |
|-----------|------------|--------------|------------|
| **Phase 1 Complete** | Week 1 | Core infrastructure, Kiro setup | Steering files, hooks setup |
| **Phase 2 Complete** | Week 3 | Intelligent routing, fusion | Automation hooks, workflow |
| **Phase 3 Complete** | Week 4 | LLM integration, optimization | Kiro optimization guidance |
| **Phase 4 Complete** | Week 5 | Production deployment | Submission preparation |
| **MVP Release** | Week 2 | Minimum viable product | Basic Kiro integration |
| **Beta Release** | Week 4 | Feature complete version | Full Kiro workflow |
| **Kiroween Submission** | Week 5 | Final submission | Kiro showcase complete |

## 🎥 Demo Video Outline (2 Minutes)

### Part 1: Problem & Solution (30 seconds)
- Traditional RAG limitations
- Hybrid approach benefits
- Kiro-powered development

### Part 2: Kiro Workflow (60 seconds)
- Spec-driven development
- Steering files in action
- Agent hooks automation
- AI collaboration features

### Part 3: Live Demo (30 seconds)
- Query processing
- Dual-engine retrieval
- Fusion results
- Final answer generation

---

*This specification is a living document developed with Kiro for the Kiroween 2026 Hackathon.*  
*Last updated: November 4, 2026 | Submission Period: October 30 - December 4, 2026*  
*Version: 2.0.0 | Author: Kiro AI Assistant | For: The Alchemist's Chimera Project*