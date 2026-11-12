# Implementation Plan

## Overview

This document outlines the implementation tasks for extending The Alchemist's Chimera with a Dynamic PDF-to-RDF Ingestion Pipeline with Human-in-the-Loop (HITL) Governance, Streamlit Web UI, and Hugging Face Spaces deployment. Tasks are organized by component and follow the requirements-first workflow.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Core Ingestion Engine",
      "tasks": ["1", "2", "3", "4", "5"],
      "description": "Foundation components for PDF parsing and triple extraction"
    },
    {
      "name": "Ingestion Pipeline Orchestrator",
      "tasks": ["5.1"],
      "depends_on": ["1", "2", "3", "4", "5"],
      "description": "Orchestrator that coordinates all ingestor components"
    },
    {
      "name": "Staging & Data Preparation",
      "tasks": ["6", "7"],
      "depends_on": ["1", "2", "3", "4", "5", "5.1"],
      "description": "HITL workflow and sample data preparation"
    },
    {
      "name": "Streamlit UI Foundation",
      "tasks": ["8"],
      "depends_on": ["6"],
      "description": "Basic Streamlit application setup"
    },
    {
      "name": "UI Component Implementation",
      "tasks": ["9", "10", "11"],
      "depends_on": ["8"],
      "description": "Individual tab implementations for hybrid chat, PDF upload, and KG explorer"
    },
    {
      "name": "Deployment Configuration",
      "tasks": ["12", "13", "14"],
      "depends_on": ["9", "10", "11"],
      "description": "Docker, startup scripts, and documentation updates"
    },
    {
      "name": "Compliance & Testing",
      "tasks": ["15", "16", "17", "18"],
      "depends_on": ["6", "8", "9", "10", "11"],
      "description": "HKMA compliance features, comprehensive testing, and performance optimization"
    },
    {
      "name": "Final Integration & Repository Cleanup",
      "tasks": ["19", "20", "21"],
      "depends_on": ["12", "13", "14", "15", "16", "17", "18"],
      "description": "Kiro integration, final validation, and repository cleanup"
    }
  ],
  "dependencies": {
    "2": ["1"],
    "3": ["2"],
    "4": ["3"],
    "5": ["3", "4"],
    "5.1": ["1", "2", "3", "4", "5"],
    "6": ["1", "2", "3", "4", "5", "5.1"],
    "7": ["5"],
    "8": ["6"],
    "9": ["8"],
    "10": ["8", "9"],
    "11": ["8", "9"],
    "12": ["10", "11"],
    "13": ["12"],
    "14": ["12", "13"],
    "15": ["6", "10"],
    "16": ["1", "2", "3", "4", "5", "5.1", "6", "8", "9", "10", "11"],
    "17": ["1", "2", "3", "4", "5", "5.1", "6"],
    "18": ["1", "2", "3", "4", "5", "5.1", "6", "8", "9", "10", "11"],
    "19": ["1-18"],
    "20": ["1-19"],
    "21": ["20"]
  }
}
```

## Tasks

### Phase 1: Core Ingestion Engine Implementation

- [x] 1. Implement PDF Parser & Chunker (`src/ingestor/pdf_parser.py`)
  - **Description**: Create PDF parsing component using pypdf with configurable chunking
  - **Requirements**: 1.1, 1.2
  - **Design Reference**: Components and Interfaces - PDF Parser & Chunker
  - **Implementation Details**:
    - Use `pypdf` for PDF text extraction
    - Implement configurable chunk size (default: 1000 chars) and overlap (default: 200 chars)
    - Generate unique chunk IDs with document metadata
    - Handle PDF parsing errors gracefully
    - Add progress tracking for large documents
  - **Test Tasks**:
    - Unit tests for PDF parsing with various formats
    - Property-based tests for chunk size consistency
    - Integration tests with sample PDFs

- [x] 2. Implement Entity Anchor Extractor (`src/ingestor/entity_extractor.py`)
  - **Description**: Create spaCy-based entity extractor for verified entity anchoring
  - **Requirements**: 1.3
  - **Design Reference**: Components and Interfaces - Entity Anchor Extractor
  - **Implementation Details**:
    - Integrate spaCy `en_core_web_sm` model
    - Filter to relevant entity types: ORG, PERSON, LAW, MONEY, GPE
    - Add confidence scoring for extracted entities
    - Implement entity deduplication across chunks
    - Handle spaCy model loading errors
  - **Test Tasks**:
    - Unit tests for entity extraction accuracy
    - Property-based tests for entity type filtering
    - Performance tests for large text chunks

- [x] 3. Implement Triple Extractor (`src/ingestor/triple_extractor.py`)
  - **Description**: Create guided LLM component for RDF triple extraction
  - **Requirements**: 1.4, 1.5, 1.6
  - **Design Reference**: Components and Interfaces - Triple Extractor
  - **Implementation Details**:
    - Integrate Ollama with `qwen2.5:3b` model
    - Implement dynamic ontology reading for valid classes/predicates
    - Create structured JSON prompt for triple extraction
    - Add evidence quote verification (case-insensitive substring check)
    - Implement fallback predicate (`chimera:relatedTo`) handling
    - Implement sequential extraction (not parallel) to stay within Hugging Face Spaces free-tier limits (2 vCPU / 16 GB RAM)
  - **Test Tasks**:
    - Unit tests for evidence quote verification
    - Property-based tests for triple extraction completeness
    - Integration tests with Ollama service

- [x] 4. Implement Provenance Manager (`src/ingestor/provenance_manager.py`)
  - **Description**: Create component for tracking provenance metadata with URI normalization
  - **Requirements**: 1.7
  - **Design Reference**: Components and Interfaces - Provenance Manager
  - **Implementation Details**:
    - Generate unique provenance URIs for each triple
    - Attach source metadata: `chimera:sourceChunk`, `chimera:pageNumber`, timestamp
    - Implement provenance chain validation
    - Add serialization/deserialization for provenance data
    - Create audit trail for extraction operations
    - **URI Normalization**: Convert plain-text entity names into valid `chimera:` URIs while preserving original text as `rdfs:label` triples
    - Implement `normalize_to_uri()` method: converts spaces and special characters to valid URI format
    - Implement `create_label_triple()` method: creates `rdfs:label` triple for normalized URIs
    - Ensure RDFLib and pyshacl never fail on spaces or special characters
  - **Test Tasks**:
    - Unit tests for provenance URI generation and URI normalization
    - Property-based tests for provenance chain integrity and label preservation
    - Integration tests with extraction pipeline
    - URI normalization tests: "Bank of America" → "chimera:Bank_of_America", "Basel III" → "chimera:Basel_III"

- [x] 5. Implement SHACL Validator (`src/ingestor/shacl_validator.py`)
  - **Description**: Create SHACL validation component with pyshacl
  - **Requirements**: 1.8, 1.9
  - **Design Reference**: Components and Interfaces - SHACL Validator
  - **Implementation Details**:
    - Integrate `pyshacl` for SHACL validation
    - Load SHACL shapes from `ontology/shapes.ttl`
    - Generate generic structural shapes for dynamic entities
    - Tag triples as VALID or QUARANTINED with error messages
    - Implement shape inference for unknown predicates
    - Add validation caching for performance
  - **Test Tasks**:
    - Unit tests for SHACL validation logic
    - Property-based tests for validation consistency
    - Integration tests with ontology shapes

### Phase 1a: Ingestion Pipeline Orchestrator

- [x] 5.1. Implement Ingestion Pipeline Orchestrator (`src/ingestor/pipeline.py`)
  - **Description**: Create orchestrator that coordinates all 5 ingestor components with vector store integration
  - **Requirements**: Integration requirements from design.md
  - **Design Reference**: Components and Interfaces - Ingestion Pipeline
  - **Implementation Details**:
    - Create `IngestionPipeline` class that coordinates: PDF Parser, Entity Extractor, Triple Extractor, Provenance Manager, SHACL Validator, Staging Manager, and Vector Store
    - Implement main orchestration method `process_pdf()` with complete workflow:
      1. Parse PDF into chunks
      2. Insert chunks into Vector Store for hybrid retrieval
      3. Process each chunk through extraction pipeline (entities → triples → provenance → validation)
      4. Perform evidence grounding check (verbatim substring verification)
      5. Send validated/quarantined triples to Staging Manager
    - Implement evidence quote verification: check case-insensitive substring presence in source chunk
    - Integrate with existing `VectorStore` from `src/vector_store.py` for immediate hybrid retrieval availability
    - Handle errors and provide comprehensive progress tracking
    - Process chunks sequentially for Ollama calls (not parallel) to respect Hugging Face Spaces resource limits
  - **Test Tasks**:
    - Unit tests for orchestration logic and evidence grounding
    - Integration tests with all ingestor components
    - End-to-end tests with sample PDFs
    - Performance tests for parallel processing
    - Error handling and recovery tests

### Phase 2: Staging & HITL Workflow Implementation

- [x] 6. Implement Staging Manager (`src/staging_manager.py`)
  - **Description**: Create human-in-the-loop approval workflow manager with live reload functionality
  - **Requirements**: 2.1-2.8
  - **Design Reference**: Components and Interfaces - Staging Manager
  - **Implementation Details**:
    - Implement staging storage in JSON and TTL formats
    - Create approval workflow with user attribution
    - Add triple editing functionality before approval
    - Implement rejection with reason tracking
    - Create auto-approval for VALID triples
    - Add transaction semantics for approval operations
    - Pre-populate sample data (HKMA/Basel III documents)
    - **Live Reload Functionality**: Implement `approve_triple()` method that triggers live reload on active GraphStore instance
    - When triple is approved:
      1. Add approval metadata (user, timestamp, notes)
      2. Merge into approved knowledge graph file
      3. Trigger `graph_store.reload_from_file()` for immediate availability
      4. Remove from staging storage
    - Ensure newly approved triples are immediately queryable in Hybrid Chat tab without restarting Streamlit
    - Implement `_merge_into_approved_kg()` for TTL serialization with provenance
    - Handle concurrent modifications and ensure data consistency
  - **Test Tasks**:
    - Unit tests for staging operations and live reload functionality
    - Property-based tests for approval workflow consistency
    - Integration tests with knowledge graph updates
    - Live reload tests: verify approved triples are immediately queryable
    - Concurrent modification tests

- [x] 7. Create Sample Data & Ontology Extensions
  - **Description**: Prepare sample regulatory documents and extend ontology
  - **Requirements**: 2.7, 2.8
  - **Implementation Details**:
    - Create sample HKMA/Basel III PDFs in `data/input/`
    - Extend `ontology/finance-ontology.ttl` with regulatory concepts
    - Create comprehensive SHACL shapes in `ontology/shapes.ttl`
    - Pre-populate `data/graphs/approved_kg.ttl` with sample knowledge
    - Add `chimera` namespace definitions for provenance
    - Create documentation for sample data structure
  - **Test Tasks**:
    - Validation tests for ontology consistency
    - Sample data integrity checks
    - Knowledge graph query tests

### Phase 3: Streamlit Web UI Implementation

- [x] 8. Implement Streamlit Application (`app.py`)
  - **Description**: Create main Streamlit web interface
  - **Requirements**: 3.1-3.8
  - **Design Reference**: Components and Interfaces - Streamlit UI Components
  - **Implementation Details**:
    - Set up dark-themed Streamlit app on port 7860
    - Implement three-tab layout: Hybrid Chat, Surgeon's Table, KG Explorer
    - Add session state management for user interactions
    - Create responsive layout with sidebar navigation
    - Implement sidebar role selector (e.g., "Compliance Officer (Demo)" / "Risk Auditor") for audit trail attribution
    - Add user role tracking for HITL approval attribution
    - Add progress indicators for long operations
  - **Test Tasks**:
    - UI component tests
    - Session state management tests
    - Responsive layout tests

- [x] 9. Implement Hybrid Chimera Chat Tab
  - **Description**: Create query interface using existing hybrid retriever
  - **Requirements**: 3.2, 3.3
  - **Implementation Details**:
    - Integrate existing `src/router.py`, `src/fusion.py`, and `src/response_generator.py`
    - Create query input with auto-completion
    - Implement visual breakdown of α(t) weight
    - Display SPARQL/RDF graph hits with provenance links
    - Show ChromaDB vector chunks side-by-side
    - Add query history and favorites
    - Implement result citation display
  - **Test Tasks**:
    - Query processing integration tests
    - Visualization component tests
    - Performance tests for real-time updates

- [x] 10. Implement Surgeon's Table Tab (PDF Upload & HITL)
  - **Description**: Create PDF upload and triple approval interface
  - **Requirements**: 3.4, 3.5, 3.8
  - **Implementation Details**:
    - Implement PDF file upload with drag-and-drop
    - Create progress tracking for extraction pipeline
    - Build interactive editable staging table (`st.data_editor`)
    - Add columns: Subject, Predicate, Object, Evidence Quote, SHACL Status
    - Implement bulk actions: approve selected, reject selected, edit multiple
    - Add filtering and sorting for staging table
    - Create one-click auto-approval for VALID triples
  - **Test Tasks**:
    - File upload integration tests
    - Table editing functionality tests
    - Bulk operation tests

- [x] 11. Implement Live Knowledge Graph Explorer Tab
  - **Description**: Create interactive KG visualization interface
  - **Requirements**: 3.6, 3.7
  - **Implementation Details**:
    - Integrate `pyvis` or `streamlit-agraph` for graph visualization
    - Implement interactive subgraph exploration
    - Highlight newly stitched nodes in visualization
    - Add node/edge filtering and search
    - Create provenance trail visualization
    - Implement graph export functionality (PNG, PDF)
    - Add timeline view for knowledge evolution
  - **Test Tasks**:
    - Visualization rendering tests
    - Interaction functionality tests
    - Performance tests for large graphs

### Phase 4: Deployment & Infrastructure

- [x] 12. Update Docker Configuration
  - **Description**: Modify Dockerfile for Hugging Face Spaces deployment
  - **Requirements**: 4.1-4.8
  - **Implementation Details**:
    - Update `Dockerfile` with Ollama installation
    - Add system dependencies: gcc, g++, curl
    - Install Python packages: streamlit, pypdf, pyvis, streamlit-agraph
    - Download spaCy model in Docker build
    - Create data directory structure
    - Copy sample data and ontology
    - Expose port 7860 for Hugging Face Spaces
    - Add health check endpoint
    - Add environment variables for Hugging Face Spaces compatibility:
      - ENV OLLAMA_MODELS=/app/.ollama/models
      - ENV HF_HOME=/app/.cache
    - Set proper permissions for UID 1000 (Hugging Face Spaces default)
    - Create necessary directories with correct ownership
  - **Test Tasks**:
    - Docker build tests
    - Container runtime tests
    - Port exposure tests

- [x] 13. Create Start Script (`start.sh`)
  - **Description**: Create startup script for Hugging Face Spaces
  - **Requirements**: 4.3, 4.4
  - **Implementation Details**:
    - Start `ollama serve` in background
    - Wait for Ollama service readiness
    - Pull `qwen2.5:3b` model if not cached
    - Launch Streamlit on port 7860
    - Implement process monitoring and cleanup
    - Add logging for startup process
    - Create environment variable configuration
    - Create directories with proper permissions for UID 1000:
      - /app/.ollama/models
      - /app/.cache
      - /app/data
    - Set environment variables to prevent PermissionDenied errors:
      - OLLAMA_MODELS=/app/.ollama/models
      - HF_HOME=/app/.cache
  - **Test Tasks**:
    - Script execution tests
    - Service startup tests
    - Error handling tests

- [x] 14. Update Documentation
  - **Description**: Update README and add deployment instructions
  - **Requirements**: 4.5, 4.6, 5.6, 5.7, 5.8
  - **Implementation Details**:
    - Update root `README.md` with new features
    - Add Hugging Face Spaces deployment instructions
    - Include HKMA regulatory governance notes
    - Create user guide for HITL workflow
    - Add API documentation for new components
    - Create troubleshooting guide
    - Update contribution guidelines
  - **Test Tasks**:
    - Documentation build tests
    - Link validation tests
    - Example verification tests

### Phase 5: HKMA Compliance & Testing

- [x] 15. Implement Compliance Features
  - **Description**: Add HKMA GenAI Sandbox and ART Framework compliance
  - **Requirements**: 5.1-5.8
  - **Implementation Details**:
    - Ensure 100% air-gapped operation verification
    - Implement deterministic guardrail testing
    - Create provenance audit trail system
    - Add human decision logging and attribution
    - Implement "Surgeon's Table" workflow validation
    - Create AI-assisted extraction decision documentation
    - Add transparency features for hybrid retrieval
    - Implement regulatory audit support logging
  - **Test Tasks**:
    - Air-gapped operation tests
    - Guardrail effectiveness tests
    - Audit trail completeness tests

- [x] 16. Create Comprehensive Test Suite
  - **Description**: Implement all required tests for new components
  - **Requirements**: 6.1-6.8
  - **Implementation Details**:
    - Create `tests/unit/test_ingestor.py` with verbatim quote filter tests
    - Add SHACL quarantine gate tests
    - Implement property-based tests for evidence grounding
    - Create integration tests for complete pipeline including IngestionPipeline
    - Add performance tests for PDF processing
    - Implement Kiro hook compatibility tests
    - Ensure all tests pass existing `.kiro/hooks/` validation
    - Achieve 80%+ test coverage for new code
  - **Test Tasks**:
    - Test suite execution
    - Coverage reporting
    - Kiro hook validation

- [x] 17. Implement Performance Optimization
  - **Description**: Optimize system for production use
  - **Requirements**: 7.1-7.8
  - **Implementation Details**:
    - Implement parallel chunk processing in IngestionPipeline
    - Add caching for ontology and SHACL shapes
    - Note: Ollama must remain sequential (not parallel) for Hugging Face Spaces free-tier compatibility
    - Implement streaming PDF parsing
    - Add connection pooling for database operations
    - Create performance monitoring dashboard
    - Implement resource usage limits
    - Add configuration for batch sizes and timeouts
  - **Test Tasks**:
    - Performance benchmark tests
    - Memory usage profiling
    - Concurrent operation tests

- [x] 18. Implement Error Handling & Resilience
  - **Description**: Add comprehensive error handling and recovery
  - **Requirements**: 8.1-8.8
  - **Implementation Details**:
    - Implement graceful PDF parsing failure handling
    - Add Ollama service retry with exponential backoff
    - Create SHACL validation error recovery
    - Implement staging file corruption recovery
    - Add comprehensive logging with severity levels
    - Create health check endpoints for all components including IngestionPipeline
    - Implement transaction semantics for approvals
    - Add recovery mechanisms for interrupted processes
  - **Test Tasks**:
    - Error injection tests
    - Recovery mechanism tests
    - Health check validation tests

### Phase 6: Kiro Integration & Finalization

- [x] 19. Integrate with Kiro Workflow
  - **Description**: Ensure full Kiro integration and compliance
  - **Requirements**: 6.1-6.8
  - **Implementation Details**:
    - Match existing class interfaces from `src/models.py`
    - Pass `.kiro/hooks/validate-ontology.json` validation
    - Pass `.kiro/hooks/run-tests.json` automated testing
    - Pass `.kiro/hooks/lint-code.json` code quality checks
    - Align with `.kiro/steering/coding_standards.md`
    - Follow `.kiro/steering/project_guidelines.md` patterns
    - Document Kiro-assisted development steps
    - Update spec with implementation progress
  - **Test Tasks**:
    - Kiro hook execution tests
    - Code style compliance tests
    - Interface compatibility tests
  - **Implementation Progress**:
    - Added portable Kiro hook runners for tests, linting, and ontology validation.
    - Removed the ontology hook's unsupported `--verbose` flag and implicit package installation.
    - Added canonical Pydantic ingestion contracts to `src/models.py` while preserving the existing runtime ingestor interfaces.
    - Added focused hook execution, style, and model compatibility tests in `tests/test_task19_kiro_workflow.py`.
    - Documented the Kiro-assisted workflow in `docs/kiro_usage.md` and linked it from the documentation navigation.
    - The full repository hook remains an environment-wide quality gate. Existing end-to-end retrieval and legacy formatting issues are reported separately rather than changed as part of Task 19.

- [x] 20. Final Integration & Validation
  - **Description**: Complete end-to-end integration and validation
  - **Implementation Details**:
    - Run full test suite including new and existing tests
    - Perform end-to-end PDF ingestion workflow test
    - Validate Streamlit UI functionality across all tabs
    - Test Docker container build and runtime
    - Verify Hugging Face Spaces deployment readiness
    - Ensure HKMA compliance requirements are met
    - Perform performance testing with sample regulatory documents
    - Create final documentation and user guides
  - **Test Tasks**:
    - End-to-end integration tests
    - Deployment readiness tests
    - Compliance validation tests

### Phase 7: Repository Cleanup and Documentation Consistency

- [ ] 21. Clean Up Tracked Artifacts and Reconcile Approval Documentation
  - **Description**: Remove repository clutter and align the README's approval-flow wording with the implemented default behavior.
  - **Requirements**: 4.5, 5.4, 6.7, 6.8
  - **Implementation Subtasks**:
    - Remove the tracked root `.DS_Store` file and confirm `.DS_Store` is covered by `.gitignore`.
    - Review the six tracked root scratch scripts (`test_pdf_parser.py`, `test_pdf_parser_fixed.py`, `test_pipeline.py`, `test_provenance_manager.py`, `test_staging_manager.py`, and `test_staging_manager_minimal.py`); move useful coverage into the dedicated `tests/` area or delete each script when redundant.
    - Update the README approval-flow wording to match `app.py` and `IngestionPipeline`: the default pipeline requires attributed human approval and does not auto-merge `VALID` records into the live knowledge graph.
    - Preserve any explicitly documented legacy opt-in auto-approval behavior only where it remains accurate for direct `StagingManager` use.
  - **Test Subtasks**:
    - Verify repository status and tracked-file queries show no tracked `.DS_Store` and no obsolete root scratch scripts.
    - Run the affected test suites and documentation checks, including a focused assertion that the default ingestion path keeps `VALID` records pending until attributed human approval.
    - Confirm README statements about default approval behavior agree with the `app.py` and `IngestionPipeline` configuration.

## Notes

### Kiro Integration Notes
- All new code must follow existing coding standards and patterns
- Use type hints and comprehensive docstrings as per project guidelines
- Update Kiro hooks to include new test modules and validation steps
- Document Kiro-assisted development in commit messages and documentation

### Performance Considerations
- Implement parallel processing for PDF chunk extraction in IngestionPipeline
- Use caching for frequently accessed ontology data
- Batch LLM calls to optimize Ollama utilization
- Implement pagination for large staging tables
- Use lazy loading for graph visualization components

### Security Considerations
- Validate all uploaded PDF files for malicious content
- Implement proper input sanitization for user-editable fields
- Ensure no sensitive data leaves the local container
- Add audit logging for all user interactions
- Implement access controls for different user roles

### Compliance Requirements
- Maintain 100% air-gapped operation for HKMA compliance
- Implement deterministic guardrails through SHACL validation
- Ensure full provenance tracking from source to approved triple
- Require human approval before knowledge graph updates
- Provide transparency into AI-assisted extraction decisions

### Testing Strategy
- Implement property-based tests for core correctness properties including URI normalization and live reload
- Create comprehensive unit tests for all new components including IngestionPipeline
- Perform integration tests for complete workflow
- Include performance tests for large document processing
- Test error handling and recovery scenarios

### Deployment Requirements
- Single Docker container deployment for Hugging Face Spaces
- Port 7860 exposure for Streamlit compatibility
- Ollama service running in background
- Pre-populated sample data for immediate functionality
- Health monitoring and automatic recovery

### Practical Constraints & Implementation Guidelines

The following practical constraints from the design document must be observed during implementation:

1. **No Login Wall (Task 8)**: For Devpost judges on Hugging Face Spaces, do not add a password/login gate. Instead, use a simple sidebar role selector (e.g., "Compliance Officer (Demo)" / "Risk Auditor") to tag HITL approvals in the audit trail.

2. **Sequential Ollama Inference (Tasks 3, 5.1, 17)**: Run Ollama qwen2.5:3b extraction sequentially (one chunk at a time) rather than parallelizing LLM calls, to stay safely within Hugging Face Spaces' 2 vCPU / 16 GB RAM free-tier limits.

3. **Hugging Face Non-Root Permissions (Tasks 12 & 13)**: Hugging Face Spaces runs containers as UID 1000. In Dockerfile and start.sh, set ENV OLLAMA_MODELS=/app/.ollama/models, ENV HF_HOME=/app/.cache, and ensure proper permissions so Ollama, sentence-transformers, and ChromaDB never hit PermissionDenied errors.
