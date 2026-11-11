# Requirements Document

## Introduction

The Dynamic PDF-to-RDF Ingestion Pipeline with Human-in-the-Loop (HITL) Governance extends The Alchemist's Chimera hybrid RAG engine with a production-grade document ingestion system. This feature enables regulatory-compliant PDF processing with deterministic symbolic guardrails (SHACL), provenance tracking, and human approval workflows before extracted knowledge enters the live knowledge graph. The system includes a Streamlit Web UI for interactive management and is deployable to Hugging Face Spaces.

## Glossary

- **System**: The Alchemist's Chimera hybrid RAG engine extended with PDF-to-RDF ingestion capabilities
- **PDF_Parser**: Component responsible for extracting text and metadata from PDF documents
- **Entity_Anchor_Extractor**: spaCy-based component that extracts verified entities to prevent LLM hallucinations
- **Triple_Extractor**: Guided LLM component that extracts RDF triples from PDF content using ontology constraints
- **Provenance_Manager**: Component that tracks source information (chunk_id, page_number, timestamp) for extracted triples
- **SHACL_Validator**: Component that validates extracted triples against SHACL shapes for structural correctness
- **Staging_Manager**: Component that manages human-in-the-loop approval workflows for extracted triples
- **Streamlit_UI**: Interactive web interface for PDF upload, triple approval, and knowledge graph exploration
- **Hybrid_Retriever**: Existing component that performs graph-vector retrieval for query processing
- **Chimera_Ontology**: The finance ontology defining classes and predicates for regulatory knowledge representation
- **Hugging_Face_Spaces**: Deployment platform for containerized Streamlit applications
- **HKMA_GenAI_Sandbox**: Hong Kong Monetary Authority's Generative AI Sandbox framework for regulatory compliance
- **ART_Framework**: Accountability, Responsibility, and Transparency framework for AI governance

## Requirements

### Requirement 1: Dynamic Two-Tier PDF-to-RDF Ingestor

**User Story:** As a regulatory compliance officer, I want to upload PDF documents and automatically extract structured knowledge in RDF format, so that I can build a comprehensive regulatory knowledge graph without manual data entry.

#### Acceptance Criteria

1. WHEN a PDF document is uploaded, THE PDF_Parser SHALL extract text content with metadata including document name, page numbers, and chunk identifiers
2. THE PDF_Parser SHALL split documents into configurable-sized chunks with overlap for context preservation
3. THE Entity_Anchor_Extractor SHALL use spaCy (`en_core_web_sm`) to extract verified entities (`ORG`, `PERSON`, `LAW`, `MONEY`, `GPE`) from each chunk
4. THE Triple_Extractor SHALL read valid classes and predicates dynamically from the Chimera_Ontology (`ontology/finance-ontology.ttl`)
5. THE Triple_Extractor SHALL use Ollama `qwen2.5:3b` with structured JSON output to extract `(subject, predicate, object, evidence_quote)` triples grounded in spaCy entities
6. THE Triple_Extractor SHALL automatically reject any triple whose `evidence_quote` does not appear as a case-insensitive substring inside the source PDF chunk
7. THE Provenance_Manager SHALL attach `chimera:sourceChunk`, `chimera:pageNumber`, and extraction timestamp to every valid triple
8. THE SHACL_Validator SHALL validate extracted triples against `ontology/shapes.ttl` and generic structural SHACL shapes for dynamic entities
9. THE SHACL_Validator SHALL tag each triple as `VALID` or `QUARANTINED` with validation error messages
10. THE System SHALL store extracted triples in a staging area (`data/graphs/staging_triples.json/ttl`) rather than directly in the live knowledge graph

### Requirement 2: Staging & Human-in-the-Loop Approval Manager

**User Story:** As a knowledge graph curator, I want to review, edit, approve, or reject extracted triples before they enter the live knowledge graph, so that I can ensure data quality and regulatory compliance.

#### Acceptance Criteria

1. THE Staging_Manager SHALL store newly extracted triples in `data/graphs/staging_triples.json` and `.ttl` formats
2. THE Staging_Manager SHALL support approving selected triples for merging into `data/graphs/approved_kg.ttl`
3. THE Staging_Manager SHALL reload the Graph_Store with newly approved triples including `chimera:approvedBy` provenance metadata
4. WHERE a user selects to edit a triple, THE Staging_Manager SHALL allow modification of subject, predicate, and object fields before approval
5. THE Staging_Manager SHALL support rejecting or quarantining triples with specified reasons
6. THE Staging_Manager SHALL provide one-click auto-approval functionality for clean `VALID` triples
7. THE System SHALL pre-populate `data/input/` with sample HKMA/Basel III regulatory documents for immediate functionality
8. THE System SHALL pre-populate `data/graphs/approved_kg.ttl` with sample regulatory knowledge for immediate querying

### Requirement 3: Streamlit "Alchemist's Lab" Web UI

**User Story:** As an end user, I want an intuitive web interface to interact with the hybrid RAG system, manage PDF ingestion, and explore the knowledge graph, so that I can efficiently perform regulatory research and compliance tasks.

#### Acceptance Criteria

1. THE Streamlit_UI SHALL run on port `7860` with a clean, dark-themed interface
2. THE Streamlit_UI SHALL provide a "Hybrid Chimera Chat (Query & Audit)" tab with query input calling the existing Hybrid_Retriever
3. THE Streamlit_UI SHALL visually display the dynamic **α(t) weight**, **SPARQL/RDF graph hits** with provenance links, and **ChromaDB vector chunks** side-by-side
4. THE Streamlit_UI SHALL provide a "The Surgeon's Table (PDF Upload & HITL Approval)" tab with PDF upload functionality
5. THE Streamlit_UI SHALL display an interactive editable staging table (`st.data_editor`) showing `(Subject, Predicate, Object, Evidence Quote, SHACL Status)`
6. THE Streamlit_UI SHALL provide a "Live Knowledge Graph Explorer" tab with interactive subgraph visualization using `pyvis` or `streamlit-agraph`
7. THE Live_Knowledge_Graph_Explorer SHALL highlight newly stitched nodes in the visualization
8. THE Streamlit_UI SHALL show extraction progress status and real-time feedback during PDF processing

### Requirement 4: Hugging Face Spaces Deployment

**User Story:** As a developer, I want to deploy the complete system to Hugging Face Spaces as a single container, so that users can access the application without local installation.

#### Acceptance Criteria

1. THE Dockerfile SHALL install system dependencies, Python packages, Ollama, and Streamlit
2. THE Dockerfile SHALL start `ollama serve` in the background and pull `qwen2.5:3b` model if not cached
3. THE Dockerfile SHALL launch `streamlit run app.py --server.port=7860 --server.address=0.0.0.0` as the main process
4. THE System SHALL include a `start.sh` script for Hugging Face Spaces container initialization
5. THE System SHALL update the root `README.md` with Hugging Face Spaces deployment instructions
6. THE System SHALL include HKMA regulatory governance notes in the deployment documentation
7. THE Docker_Configuration SHALL expose port `7860` for Hugging Face Spaces compatibility
8. THE Docker_Configuration SHALL persist data directories (`./data`, `./models`) for knowledge preservation

### Requirement 5: HKMA GenAI Sandbox / ART Framework Compliance

**User Story:** As a regulated financial institution, I need the system to comply with HKMA GenAI Sandbox and ART Framework requirements, so that we can safely deploy AI systems for regulatory compliance tasks.

#### Acceptance Criteria

1. THE System SHALL remain 100% air-gapped and local-first with Ollama `qwen2.5:3b`, RDFLib, and ChromaDB
2. THE System SHALL enforce deterministic symbolic guardrails through SHACL validation before triple approval
3. THE System SHALL maintain full provenance links from extracted triples back to source PDF chunks
4. THE System SHALL require human approval/editing before extracted triples enter the live knowledge graph
5. THE System SHALL implement the "Surgeon's Table" staging workflow for controlled knowledge stitching
6. THE System SHALL document all AI-assisted extraction decisions with audit trails
7. THE System SHALL provide transparency into the hybrid retrieval process showing graph vs vector contributions
8. THE System SHALL support regulatory audit requirements with comprehensive logging of all user interactions

### Requirement 6: Kiro Integration & Automated Testing

**User Story:** As a developer using Kiro for the Kiroween hackathon, I want the new modules to integrate with existing Kiro workflows and pass all automated quality checks, so that I can demonstrate comprehensive Kiro feature utilization.

#### Acceptance Criteria

1. THE new modules SHALL match existing class interfaces and typing patterns from `src/models.py`
2. THE System SHALL pass existing `.kiro/hooks/validate-ontology.json` validation for new ontology extensions
3. THE System SHALL pass existing `.kiro/hooks/run-tests.json` automated testing including new unit tests
4. THE System SHALL pass existing `.kiro/hooks/lint-code.json` code quality checks
5. THE System SHALL include unit tests in `tests/unit/test_ingestor.py` for verbatim quote filter validation
6. THE System SHALL include unit tests in `tests/unit/test_ingestor.py` for SHACL quarantine gate functionality
7. THE System SHALL align with `.kiro/steering/coding_standards.md` and `project_guidelines.md`
8. THE System SHALL demonstrate Kiro-assisted development through spec-driven implementation tracking

### Requirement 7: Performance & Scalability

**User Story:** As a system administrator, I need the PDF ingestion pipeline to handle regulatory documents efficiently with reasonable resource usage, so that we can process large volumes of compliance documentation.

#### Acceptance Criteria

1. WHEN processing a 100-page PDF document, THE PDF_Parser SHALL complete extraction within 5 minutes on standard hardware
2. THE Entity_Anchor_Extractor SHALL process chunks with spaCy efficiently without excessive memory usage
3. THE Triple_Extractor SHALL batch LLM calls where possible to optimize Ollama utilization
4. THE Staging_Manager SHALL handle at least 1000 triples in staging without performance degradation
5. THE Streamlit_UI SHALL remain responsive during PDF processing with progress indicators
6. THE System SHALL implement proper connection pooling and resource management for concurrent operations
7. THE System SHALL include configuration options for batch sizes, concurrency limits, and timeout settings
8. THE System SHALL log performance metrics for monitoring and optimization

### Requirement 8: Error Handling & Resilience

**User Story:** As an operator, I need the system to handle edge cases and failures gracefully with informative error messages, so that I can troubleshoot issues without system downtime.

#### Acceptance Criteria

1. WHEN PDF parsing fails due to corrupted files, THE System SHALL provide clear error messages and continue processing other documents
2. WHEN Ollama service is unavailable, THE Triple_Extractor SHALL queue extraction tasks with exponential backoff retry
3. WHEN SHACL validation encounters malformed triples, THE System SHALL quarantine them with detailed error explanations
4. WHEN the staging file becomes corrupted, THE Staging_Manager SHALL create a backup and initialize a new staging area
5. THE System SHALL implement comprehensive logging with different severity levels for debugging
6. THE System SHALL include health check endpoints for monitoring component status
7. THE System SHALL implement transaction semantics for approval operations to prevent partial updates
8. THE System SHALL provide recovery mechanisms for interrupted ingestion processes