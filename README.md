# 🎃 The Alchemist’s Chimera: Local Hybrid Graph-Vector RAG Engine

> Built for **Kiroween** — Stitching deterministic knowledge graphs and statistical vector search into a unified, zero-cloud local intelligence engine.

---

## 🔬 Overview

Traditional Retrieval-Augmented Generation (RAG) forces a false choice: 
1. **Vector Search (ChromaDB):** Great for fuzzy narrative context, but prone to hallucinations on strict relational rules, hierarchies, or regulatory lineage.
2. **Knowledge Graphs (RDF/SPARQL):** Absolute truth and precise entity relationships, but blind to unstructured conversational queries.

**The Alchemist’s Chimera** is a Frankenstein-inspired hybrid architecture that routes user queries simultaneously through both engines and fuses their outputs using a weighted intent scoring function:

$$S_{\text{hybrid}} = \alpha S_{\text{graph}} + (1 - \alpha) S_{\text{vector}}$$

---

## 🛠️ Project Architecture


alchemists-chimera/
├── .kiro/                  # Kiro AI Developer Workflow
│   ├── specs/              # Architectural specs for intent routing & fusion
│   ├── steering/           # Pydantic type-safety & PEP 8 rules
│   └── hooks/              # Automated local test execution hooks
├── src/
│   ├── router.py           # Dual-branch intent router & query planner
│   ├── graph_store.py      # RDFLib & SPARQL deterministic graph engine
│   ├── vector_store.py     # ChromaDB low-latency embedding retrieval
│   └── fusion.py           # Weighted cross-verification scoring layer
├── tests/                  # Pytest unit & integration test suites
└── requirements.txt        # Python dependency manifest


---

## 🚀 Quickstart & Local Installation

Designed for local execution (fully optimized for Apple Silicon M-series Macs and Docker container environments).

### 1. Clone & Set Up Virtual Environment
```bash
git clone [https://github.com/YOUR_USERNAME/alchemists-chimera.git](https://github.com/YOUR_USERNAME/alchemists-chimera.git)
cd alchemists-chimera

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt


