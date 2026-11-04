# 🎃 The Alchemist's Chimera: Local Hybrid Graph-Vector RAG Engine
## 🏆 Kiroween Hackathon 2026 Submission

> Built for **Kiroween 2026** — Stitching deterministic knowledge graphs and statistical vector search into a unified, zero-cloud local intelligence engine with comprehensive Kiro AI integration.

---

## 🎯 Kiroween Hackathon Compliance

### Submission Details
- **Hackathon**: Kiroween 2026
- **Submission Period**: October 30 - December 4, 2026
- **Judging Criteria**: 
  - **Potential Value** (33%): Solves real enterprise RAG limitations
  - **Implementation of Kiro** (33%): Full spec→steering→hooks workflow
  - **Creativity** (33%): Novel hybrid architecture, Frankenstein theme
- **Repository**: https://github.com/froilan-sia/alchemists-chimera
- **Demo Video**: [2-minute showcase of Kiro workflow and system functionality](https://example.com/demo-video) *(to be added)*

### Kiro Feature Showcase
This project demonstrates comprehensive Kiro AI integration:
- ✅ **Spec-Driven Development**: Living specification with task tracking
- ✅ **Steering Files**: Coding standards, architecture patterns, workflows
- ✅ **Agent Hooks**: Automated validation, testing, and quality gates
- ✅ **AI Collaboration**: Kiro as co-developer throughout implementation
- ✅ **MCP Readiness**: Prepared for external tool integration

---

## 🔬 Overview

Traditional Retrieval-Augmented Generation (RAG) forces a false choice: 
1. **Vector Search (ChromaDB):** Great for fuzzy narrative context, but prone to hallucinations on strict relational rules, hierarchies, or regulatory lineage.
2. **Knowledge Graphs (RDF/SPARQL):** Absolute truth and precise entity relationships, but blind to unstructured conversational queries.

**The Alchemist's Chimera** is a Frankenstein-inspired hybrid architecture that routes user queries simultaneously through both engines and fuses their outputs using a weighted intent scoring function:

$$S_{\text{hybrid}} = \alpha(t) \cdot S_{\text{graph}} + (1 - \alpha(t)) \cdot S_{\text{vector}}$$

Where $\alpha(t)$ dynamically adjusts based on query type $t$, providing optimal retrieval for each use case.

---

## 🏗️ Architecture

### Hybrid Retrieval Pipeline
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   User Query    │────▶│  Intent Router  │────▶│  Graph Engine   │
│                 │     │  (α selection)  │     │  (RDFLib/SPARQL)│
└─────────────────┘     └─────────────────┘     └────────┬────────┘
         │                        │                       │
         │                        ▼                       │
         │              ┌─────────────────┐               │
         └─────────────▶│  Vector Engine  │◀──────────────┘
                        │   (ChromaDB)    │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │   Fusion Layer  │
                        │ (Weighted Score)│
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │  LLM Generation │
                        │   (Ollama)      │
                        └─────────────────┘
```

### Query Type Classification & α Weights
| Query Type | α (Graph Weight) | Characteristics | Example |
|------------|------------------|-----------------|---------|
| **Entity-Relationship** | 0.8 | Specific entities, hierarchies | "What subsidiaries does Bank of America own?" |
| **Regulatory** | 0.7 | Compliance, legal frameworks | "Basel III capital requirements?" |
| **Semantic** | 0.3 | Conceptual, abstract context | "Impact of quantitative easing on inflation" |
| **Hybrid** | 0.5 | Mixed entity and conceptual | "Apple stock performance after earnings call" |

---

## 🛠️ Project Structure with Kiro Integration

```
alchemists-chimera/
├── .kiro/                          # Kiro AI Developer Workflow
│   ├── specs/                      # Architectural specs & task tracking
│   │   └── hybrid_rag_spec.md      # Living specification (283 lines)
│   ├── steering/                   # Development standards & guidelines
│   │   ├── coding_standards.md     # PEP 8, type hints, documentation
│   │   ├── project_guidelines.md   # Architecture patterns, data models  
│   │   └── kiro_workflow.md        # Kiro development workflow
│   └── hooks/                      # Automated workflows (JSON configs)
│       ├── validate-ontology.json  # SHACL validation on .ttl files
│       ├── run-tests.json          # Automated testing on .py files
│       ├── lint-code.json          # Code quality checks on save
│       └── init-env.json           # Environment setup on session start
├── src/                            # Source code
│   ├── __init__.py
│   ├── router.py                   # Dual-branch intent router
│   ├── graph_store.py              # RDFLib & SPARQL graph engine
│   ├── vector_store.py             # ChromaDB vector engine
│   ├── fusion.py                   # Weighted scoring fusion
│   ├── intent_classifier.py        # Query type detection
│   ├── context_builder.py          # LLM prompt assembly
│   └── response_generator.py       # Ollama integration
├── tests/                          # Test suites
│   ├── unit/                       # Unit tests
│   ├── integration/                # Integration tests
│   └── test_fusion.py              # Fusion engine tests
├── ontology/                       # Finance ontology
│   ├── finance-ontology.ttl        # OWL ontology
│   └── shapes.ttl                  # SHACL validation shapes
├── data/                           # Local data storage
├── models/                         # ML models and embeddings
├── docs/                           # Documentation
│   └── kiro_usage.md              # Kiro feature documentation
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container configuration
├── docker-compose.yml              # Local deployment
└── README.md                       # This file
```

---

## 🚀 Quickstart & Local Installation

### 1. Clone & Setup
```bash
# Clone repository
git clone https://github.com/froilan-sia/alchemists-chimera.git
cd alchemists-chimera

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install additional dependencies
pip install sentence-transformers spacy scikit-learn ollama pyshacl

# Download spaCy model
python -m spacy download en_core_web_sm
```

### 2. Initialize Ollama (Local LLM)
```bash
# Install Ollama (if not installed)
# See: https://ollama.ai/

# Pull required model
ollama pull qwen2.5:3b

# Verify installation
ollama list
```

### 3. Run Kiro Development Environment
```bash
# Start Kiro session (hooks will auto-initialize)
# The init-env hook will:
# 1. Check dependencies
# 2. Create necessary directories
# 3. Display project overview
# 4. Provide next steps
```

### 4. Development Workflow
```bash
# Kiro hooks automatically:
# - Validate ontology on .ttl file save
# - Run tests on .py file save  
# - Lint code on .py file save

# Manual testing
pytest tests/ -v
python -m black --check .
python -m isort --check-only .
```

---

## 🔧 Kiro Development Features

### Automated Workflows
| Hook | Trigger | Action | Purpose |
|------|---------|--------|---------|
| `validate-ontology` | Save .ttl | SHACL validation | Data quality assurance |
| `run-tests` | Save .py | Run pytest | Prevent regressions |
| `lint-code` | Save .py | Code formatting | Enforce standards |
| `init-env` | Session start | Environment setup | Project onboarding |

### Steering Files
1. **`coding_standards.md`** - PEP 8, type hints, documentation standards
2. **`project_guidelines.md`** - Architecture patterns, data models, testing
3. **`kiro_workflow.md`** - Kiro development procedures, demo preparation

### Spec-Driven Development
- **`hybrid_rag_spec.md`** - 283-line living specification
- Task breakdown into 4 phases (8 weeks)
- Progress tracking against spec tasks
- Judging criteria alignment documented

---

## 📦 Core Components

### 1. Intent Classifier (`src/intent_classifier.py`)
- Rule-based + ML query type detection
- Named Entity Recognition (NER) for entity queries
- Keyword matching for regulatory terms
- Confidence scoring for routing decisions

### 2. Dual-Branch Router (`src/router.py`)
- Dynamic α parameter calculation
- Configurable routing thresholds
- Fallback mechanisms
- Performance monitoring

### 3. Graph Store Engine (`src/graph_store.py`)
- RDFLib integration with existing finance ontology
- SPARQL 1.1 query execution
- Inference engine support (HermiT/Pellet)
- SHACL validation hooks
- Subgraph extraction for context

### 4. Vector Store Engine (`src/vector_store.py`)
- ChromaDB with local persistence
- Sentence-transformers embeddings
- Document chunking strategies
- Metadata filtering
- Reciprocal Rank Fusion (RRF) support

### 5. Fusion Orchestrator (`src/fusion.py`)
- Weighted scoring: αS_graph + (1-α)S_vector
- Reciprocal Rank Fusion (RRF)
- Cross-encoder re-ranking (optional)
- Deduplication and confidence calibration

### 6. LLM Integration (`src/response_generator.py`)
- Ollama API integration
- Qwen2.5:3b model
- Streaming response handling
- Citation inclusion
- Response validation

---

## 🧪 Testing Strategy

### Test Categories
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests  
pytest tests/integration/ -v

# Performance tests
python tests/performance/benchmark.py

# End-to-end tests
python tests/e2e/test_pipeline.py
```

### Test Coverage Goals
- **Unit tests**: 80%+ coverage
- **Integration tests**: Critical paths covered
- **Performance tests**: Latency benchmarks
- **Quality tests**: Hallucination rate measurement

### Automated Testing (Kiro Hooks)
- Tests run automatically on file save
- Failures block commits (optional)
- Coverage reports generated
- Performance regression detection

---

## 🚀 Deployment

### Local Development
```bash
# Development mode
python -m uvicorn src.api.main:app --reload --port 8000

# Or use CLI
python src/cli/main.py --query "Your question here"
```

### Docker Deployment
```bash
# Build and run
docker build -t alchemists-chimera .
docker run -p 8000:8000 alchemists-chimera

# Or use docker-compose
docker-compose up -d
```

### Production Considerations
- Resource monitoring (CPU, memory, disk)
- Log aggregation (ELK stack)
- Metrics collection (Prometheus)
- Health checks and alerts
- Backup strategies for local data

---

## 📊 Performance Metrics

### Target Benchmarks
| Metric | Target | Current |
|--------|--------|---------|
| Query Processing | < 5s P95 | TBD |
| Retrieval Latency | < 2s P95 | TBD |
| LLM Response | < 10s P95 | TBD |
| Memory Usage | < 2GB | TBD |
| Accuracy | > 85% | TBD |

### Quality Metrics
- **Hallucination Rate**: < 5%
- **Citation Accuracy**: > 90%
- **Context Relevance**: > 80%
- **Response Coherence**: > 85%

---

## 🔗 Integration Points

### Existing Code Reuse
1. **Finance Ontology**: From `finance-ontology-rag` repository
2. **SHACL Validation**: Existing validation patterns
3. **Entity Extraction**: LLM extraction workflows
4. **Dual-Branch Patterns**: Fusion logic adaptation

### Kiro Integration
1. **Spec Tracking**: GitHub Issues linked to spec tasks
2. **CI/CD Pipeline**: GitHub Actions with Kiro-aware steps
3. **Documentation**: Auto-generated from code and spec
4. **Quality Gates**: Steering-enforced standards

---

## 🎥 Demo Video Outline (2 Minutes)

### Part 1: Problem & Solution (30s)
- Traditional RAG limitations (hallucinations vs. rigidity)
- Hybrid approach benefits
- Kiro-powered development story

### Part 2: Kiro Workflow (60s)
- Spec-driven development (show spec document)
- Steering files in action (coding standards)
- Agent hooks demonstration (auto-testing on save)
- AI collaboration (live code generation)

### Part 3: System Demo (30s)
- Query processing showcase
- Dual-engine retrieval visualization
- Fusion results display
- Final answer with citations

---

## 📈 Development Roadmap

### Phase 1: Foundation (Week 1-2)
- Kiro project configuration
- Graph engine integration
- Vector engine setup
- Basic query interface

### Phase 2: Intelligence (Week 3-4)
- Intent classifier implementation
- Router development
- Fusion engine
- Context assembly

### Phase 3: Enhancement (Week 5-6)
- LLM integration
- Performance optimization
- Quality assurance
- Kiro workflow showcase

### Phase 4: Productionization (Week 7-8)
- API layer development
- Deployment configuration
- Kiroween submission preparation
- Documentation completion

---

## 👥 Team & Contributions

### Primary Developer
- **Froilan Sia**: Project lead, architecture, implementation
- **Kiro AI**: Co-developer, code generation, review, optimization

### Domain Expertise
- **Finance Ontology**: Existing work from `finance-ontology-rag`
- **RAG Systems**: Hybrid architecture design
- **Kiro Platform**: Comprehensive feature utilization

### Collaboration
- Open to contributions via GitHub
- Issue tracking and task management
- Community feedback welcome

---

## 📚 References & Resources

### Project Links
- **Repository**: https://github.com/froilan-sia/alchemists-chimera
- **Finance Ontology**: https://github.com/froilan-sia/finance-ontology-rag
- **Kiroween Hackathon**: https://kiroween.devpost.com/
- **Kiro Documentation**: https://kiro.dev/docs

### Technical Resources
- **RDFLib**: https://rdflib.readthedocs.io/
- **ChromaDB**: https://docs.trychroma.com/
- **Ollama**: https://github.com/ollama/ollama
- **SHACL**: https://www.w3.org/TR/shacl/

### Research & Inspiration
- HybridRAG: Graph + Vector fusion patterns
- Enterprise RAG architectures (2026 patterns)
- Local-first AI systems
- Frankenstein-inspired design (modular, hybrid)

---

## 🏆 Kiroween Judging Alignment

### Potential Value (33%)
- Solves real enterprise RAG limitations
- Local-first architecture (privacy, cost)
- Hybrid approach (accuracy + flexibility)
- Production-ready design

### Implementation of Kiro (33%)
- Spec-driven development workflow
- Steering files for standards
- Agent hooks for automation
- AI collaboration throughout
- Comprehensive documentation

### Creativity (33%)
- Novel hybrid architecture
- Frankenstein-inspired design
- Dynamic α parameter weighting
- Integration of existing ontology work
- Kiro feature innovation

---

## 📝 License

This project is developed for the Kiroween 2026 hackathon. All code is open source under the MIT License.

See `LICENSE` file for details.

---

## 🙏 Acknowledgments

- **Kiro Team** for creating an amazing AI development platform
- **Devpost** for hosting Kiroween hackathon
- **Open source community** for tools and libraries
- **Existing finance ontology work** as foundation

---

*Built with ❤️ and Kiro for Kiroween 2026*  
*Submission Period: October 30 - December 4, 2026*  
*Last Updated: November 4, 2026 | Version: 2.0.0*