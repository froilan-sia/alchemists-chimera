# Design Document

## Overview

This design document specifies the architecture, components, and implementation details for the Dynamic PDF-to-RDF Ingestion Pipeline with Human-in-the-Loop (HITL) Governance, Streamlit Web UI, and Hugging Face Spaces deployment. The design builds upon the existing Alchemist's Chimera hybrid RAG engine, extending it with regulatory-compliant document ingestion capabilities while maintaining alignment with HKMA GenAI Sandbox and ART Framework requirements.

## Architecture

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Streamlit Web UI (app.py)                           │
│  Port 7860 | Dark Theme | Three Tabs                                    │
└────────────┬────────────────────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────────────────┐
│                  API Layer & Request Router                              │
│  • Streamlit Callbacks                                                  │
│  • Session State Management                                             │
│  • Authentication & Authorization                                       │
└────────────┬────────────────────────────────────────────────────────────┘
             │
    ┌────────▼────────┐       ┌────────▼────────┐       ┌────────▼────────┐
    │                 │       │                 │       │                 │
    │ PDF Ingestion   │       │  Hybrid Chat    │       │   KG Explorer   │
    │ Pipeline        │◄─────►│   Interface     │◄─────►│   Interface     │
    │                 │       │                 │       │                 │
    └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
             │                         │                         │
    ┌────────▼─────────────────────────▼─────────────────────────▼────────┐
    │                   Core Engine Components                            │
    │  • PDF Parser & Chunker                                            │
    │  • Entity Anchor Extractor (spaCy)                                 │
    │  • Triple Extractor (Ollama qwen2.5:3b)                            │
    │  • Provenance Manager                                              │
    │  • SHACL Validator                                                 │
    │  • Staging Manager                                                 │
    │  • Ingestion Pipeline (Orchestrator)                               │
    └────────────────────────────────────────────────────────────────────┘
             │                         │                         │
    ┌────────▼────────┐       ┌────────▼────────┐       ┌────────▼────────┐
    │                 │       │                 │       │                 │
    │  Data Stores    │       │ Existing RAG    │       │  Visualization  │
    │  • Staging JSON │       │ Components      │       │  • PyVis        │
    │  • Approved TTL │       │ • Graph Store   │       │  • Streamlit-  │
    │  • ChromaDB     │       │ • Vector Store  │       │    Agraph       │
    │                 │       │ • Fusion Engine │       │                 │
    └─────────────────┘       └─────────────────┘       └─────────────────┘
```

### System Architecture Principles

1. **Local-First Compliance**: All components run locally within the Docker container with no external dependencies for core functionality
2. **Modular Design**: Each component is independently testable and replaceable
3. **Provenance Tracking**: Full chain of custody from source PDF to approved knowledge graph triple
4. **Human-in-the-Loop**: No automatic updates to live knowledge graph without human approval
5. **Deterministic Guardrails**: SHACL validation and evidence verification before any triple consideration
6. **Immediate Availability**: Newly approved triples are immediately queryable without system restart


## Practical Constraints & Implementation Guidelines

### 1. No Login Wall (Task 8)
For Devpost judges on Hugging Face Spaces, do not add a password/login gate. Instead, use a simple sidebar role selector (e.g., "Compliance Officer (Demo)" / "Risk Auditor") to tag HITL approvals in the audit trail.

### 2. Sequential Ollama Inference (Task 3, 5a, 17)
Run Ollama qwen2.5:3b extraction sequentially (one chunk at a time) rather than parallelizing LLM calls, so we stay safely within Hugging Face Spaces' 2 vCPU / 16 GB RAM free-tier limits.

### 3. Hugging Face Non-Root Permissions (Task 12 & 13)
Hugging Face Spaces runs containers as UID 1000. In Dockerfile and start.sh, set ENV OLLAMA_MODELS=/app/.ollama/models, ENV HF_HOME=/app/.cache, and chmod -R 777 /app so Ollama, sentence-transformers, and ChromaDB never hit PermissionDenied errors on /root/.

These constraints should be referenced in relevant tasks in tasks.md.
## Components and Interfaces

### 1. PDF Parser & Chunker (`src/ingestor/pdf_parser.py`)
```python
class PDFParser:
    """Extracts text and metadata from PDF documents."""
    
    def parse(self, pdf_path: str) -> List[DocumentChunk]:
        """Parse PDF into structured chunks with metadata."""
        pass
    
    def chunk_document(self, text: str, metadata: Dict) -> List[DocumentChunk]:
        """Split document into overlapping chunks."""
        pass
```

### 2. Entity Anchor Extractor (`src/ingestor/entity_extractor.py`)
```python
class EntityAnchorExtractor:
    """Extracts verified entities using spaCy to anchor LLM extraction."""
    
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")
    
    def extract_entities(self, chunk: DocumentChunk) -> List[Entity]:
        """Extract named entities from text chunk."""
        pass
```

### 3. Triple Extractor (`src/ingestor/triple_extractor.py`)
```python
class TripleExtractor:
    """Uses guided LLM to extract RDF triples from document chunks."""
    
    def __init__(self, ontology_path: str):
        self.ontology = self._load_ontology(ontology_path)
        self.llm_client = OllamaClient(model="qwen2.5:3b")
    
    def extract_triples(self, chunk: DocumentChunk, entities: List[Entity]) -> List[ExtractedTriple]:
        """Extract RDF triples using LLM guided by entities and ontology."""
        pass
```

### 4. Provenance Manager (`src/ingestor/provenance_manager.py`)
```python
class ProvenanceManager:
    """Manages provenance metadata for extracted triples with URI normalization."""
    
    def __init__(self):
        self.base_uri = "chimera:"
    
    def add_provenance(self, triple: ExtractedTriple) -> ProvenancedTriple:
        """Add provenance metadata to extracted triple."""
        pass
    
    def normalize_to_uri(self, text: str) -> str:
        """Normalize plain-text entity names to valid chimera: URIs.
        
        Converts spaces and special characters to valid URI format while
        preserving the original text as an rdfs:label triple.
        
        Example:
            "Bank of America" → "chimera:Bank_of_America"
            "Basel III" → "chimera:Basel_III"
            
        This ensures RDFLib and pyshacl never fail on spaces or special characters.
        """
        # Convert to snake_case, replace spaces and special chars with underscores
        normalized = text.replace(" ", "_").replace("-", "_").replace(":", "")
        normalized = re.sub(r'[^\w_]', '', normalized)
        return f"{self.base_uri}{normalized}"
    
    def create_label_triple(self, uri: str, original_text: str) -> Tuple[str, str, str]:
        """Create rdfs:label triple for the normalized URI."""
        return (uri, "rdfs:label", f'"{original_text}"')
```

### 5. SHACL Validator (`src/ingestor/shacl_validator.py`)
```python
class SHACLValidator:
    """Validates extracted triples against SHACL shapes."""
    
    def __init__(self, shapes_path: str):
        self.shapes_graph = self._load_shapes(shapes_path)
    
    def validate(self, triple: ProvenancedTriple) -> ValidationResult:
        """Validate triple against SHACL shapes."""
        pass
```

### 6. Ingestion Pipeline (`src/ingestor/pipeline.py`)
```python
class IngestionPipeline:
    """Orchestrator that coordinates all ingestor components with vector store integration."""
    
    def __init__(self, pdf_parser: PDFParser, entity_extractor: EntityAnchorExtractor,
                 triple_extractor: TripleExtractor, provenance_manager: ProvenanceManager,
                 shacl_validator: SHACLValidator, staging_manager: StagingManager,
                 vector_store: VectorStore):
        """Initialize pipeline with all required components."""
        self.pdf_parser = pdf_parser
        self.entity_extractor = entity_extractor
        self.triple_extractor = triple_extractor
        self.provenance_manager = provenance_manager
        self.shacl_validator = shacl_validator
        self.staging_manager = staging_manager
        self.vector_store = vector_store
    
    async def process_pdf(self, pdf_path: str) -> ExtractionResult:
        """Main orchestration method for PDF ingestion."""
        # 1. Parse PDF into chunks
        chunks = self.pdf_parser.parse(pdf_path)
        
        # 2. Insert chunks into vector store for hybrid retrieval
        for chunk in chunks:
            self.vector_store.add_document(
                content=chunk.content,
                metadata=chunk.metadata,
                doc_id=chunk.chunk_id
            )
        
        # 3. Process each chunk through extraction pipeline
        all_triples = []
        for chunk in chunks:
            # Extract entities
            entities = self.entity_extractor.extract_entities(chunk)
            
            # Extract triples
            extracted_triples = self.triple_extractor.extract_triples(chunk, entities)
            
            # Apply evidence grounding check (verbatim substring)
            grounded_triples = []
            for triple in extracted_triples:
                evidence_lower = triple.evidence_quote.lower()
                chunk_lower = chunk.content.lower()
                if evidence_lower in chunk_lower:
                    grounded_triples.append(triple)
                else:
                    logging.warning(f"Evidence quote not found in chunk: {triple.evidence_quote}")
            
            # Add provenance
            provenanced_triples = [self.provenance_manager.add_provenance(t) for t in grounded_triples]
            
            # SHACL validation
            for triple in provenanced_triples:
                validation_result = self.shacl_validator.validate(triple)
                triple.validation_status = "VALID" if validation_result.is_valid else "QUARANTINED"
                triple.validation_errors = validation_result.validation_errors
            
            all_triples.extend(provenanced_triples)
        
        # 4. Send to staging manager
        self.staging_manager.add_triples(all_triples)
        
        return ExtractionResult(
            chunks_processed=len(chunks),
            triples_extracted=len(all_triples),
            valid_triples=sum(1 for t in all_triples if t.validation_status == "VALID"),
            quarantined_triples=sum(1 for t in all_triples if t.validation_status == "QUARANTINED")
        )
```

### 7. Staging Manager (`src/staging_manager.py`)
```python
class StagingManager:
    """Manages human-in-the-loop approval workflow for extracted triples with live reload."""
    
    def __init__(self, staging_path: str, approved_kg_path: str, graph_store: GraphStore):
        self.staging_path = staging_path
        self.approved_kg_path = approved_kg_path
        self.graph_store = graph_store
        self._load_staging_data()
    
    def approve_triple(self, triple_id: str, user: str, notes: str = "") -> bool:
        """Approve triple and merge into approved knowledge graph with live reload.
        
        This method triggers a live reload on the active GraphStore instance so 
        newly approved triples are immediately queryable in the Hybrid Chat tab 
        without restarting Streamlit.
        """
        # 1. Load staging triple
        triple = self.staging_triples.get(triple_id)
        if not triple:
            return False
        
        # 2. Add approval metadata
        triple.approved_by = user
        triple.approval_timestamp = datetime.now()
        triple.approval_notes = notes
        triple.approval_status = "APPROVED"
        
        # 3. Merge into approved knowledge graph file
        self._merge_into_approved_kg(triple)
        
        # 4. Trigger live reload on GraphStore
        self.graph_store.reload_from_file(self.approved_kg_path)
        
        # 5. Remove from staging
        del self.staging_triples[triple_id]
        self._save_staging_data()
        
        logging.info(f"Triple {triple_id} approved by {user}, GraphStore reloaded")
        return True
    
    def _merge_into_approved_kg(self, triple: ProvenancedTriple):
        """Merge approved triple into the knowledge graph file."""
        # Read existing graph
        graph = Graph()
        graph.parse(self.approved_kg_path, format="turtle")
        
        # Add triple with provenance metadata
        subject_uri = URIRef(triple.subject if triple.subject.startswith("chimera:") else f"chimera:{triple.subject}")
        predicate_uri = URIRef(triple.predicate if triple.predicate.startswith("chimera:") else f"chimera:{triple.predicate}")
        object_uri = URIRef(triple.object) if triple.object.startswith("chimera:") else Literal(triple.object)
        
        graph.add((subject_uri, predicate_uri, object_uri))
        
        # Add provenance triples
        graph.add((subject_uri, URIRef("chimera:sourceChunk"), Literal(triple.chunk_id)))
        graph.add((subject_uri, URIRef("chimera:approvedBy"), Literal(triple.approved_by)))
        graph.add((subject_uri, URIRef("chimera:approvalTimestamp"), Literal(triple.approval_timestamp.isoformat())))
        
        # Save back to file
        graph.serialize(destination=self.approved_kg_path, format="turtle")
    
    def _load_staging_data(self):
        """Load staging data from JSON file."""
        pass
    
    def _save_staging_data(self):
        """Save staging data to JSON file."""
        pass
```

### 8. Streamlit UI Components (`app.py`)
```python
class AlchemistsLabUI:
    """Streamlit web interface for Alchemist's Chimera."""
    
    def __init__(self):
        self.setup_page_config()
        self.initialize_session_state()
    
    def render_hybrid_chat_tab(self):
        """Render hybrid chat interface tab."""
        pass
```

## Data Models

Extending existing `src/models.py` with new models:

```python
class DocumentUpload(BaseModel):
    """PDF document upload request."""
    file_name: str
    file_content: bytes
    document_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ExtractionStatus(BaseModel):
    """Status of PDF extraction process."""
    document_id: str
    status: str  # PARSING, ENTITY_EXTRACTION, TRIPLE_EXTRACTION, VALIDATION, COMPLETE
    progress: float  # 0.0 to 1.0
    extracted_triples: int = 0
    valid_triples: int = 0
    quarantined_triples: int = 0

class StagingTriple(BaseModel):
    """Triple in staging area for HITL approval."""
    id: str
    subject: str
    predicate: str
    object: str
    evidence_quote: str
    shacl_status: str  # VALID, QUARANTINED
    validation_errors: Optional[List[str]]
    source_document: str
    page_number: int
    extraction_timestamp: datetime

class DocumentChunk(BaseModel):
    """Represents a chunk of document text with metadata."""
    chunk_id: str
    content: str
    document_name: str
    page_number: int
    chunk_index: int
    metadata: Dict[str, Any]

class Entity(BaseModel):
    """Represents an extracted named entity."""
    text: str
    label: str  # ORG, PERSON, LAW, MONEY, GPE
    start_char: int
    end_char: int
    confidence: float

class ExtractedTriple(BaseModel):
    """Represents a single extracted RDF triple with provenance."""
    subject: str
    predicate: str
    object: str
    evidence_quote: str
    chunk_id: str
    page_number: int
    extraction_timestamp: datetime
    entity_anchors: List[str]

class ProvenancedTriple(BaseModel):
    """Triple with full provenance metadata."""
    triple: ExtractedTriple
    provenance_uri: str
    source_document: str
    extraction_method: str
    validation_status: str
    approval_history: List[Dict]

class ValidationResult(BaseModel):
    """Result of SHACL validation."""
    is_valid: bool
    validation_errors: List[str]
    severity: str  # INFO, WARNING, VIOLATION
    suggested_fixes: Optional[List[str]]

class ExtractionResult(BaseModel):
    """Result of PDF ingestion pipeline."""
    chunks_processed: int
    triples_extracted: int
    valid_triples: int
    quarantined_triples: int
    processing_time: float
    errors: List[str] = Field(default_factory=list)
```

## Correctness Properties

### Property 1: Evidence Grounding
**Description**: All approved triples must have evidence quotes that appear in source text.
**Type**: Invariant property
**Test Approach**: Property-based testing with generated PDF content and triples
**Implementation**: 
```python
def test_evidence_grounding():
    """Property: All approved triples have evidence quotes in source text."""
    for pdf_content, extracted_triples in generate_test_cases():
        approved_triples = approval_workflow(pdf_content, extracted_triples)
        for triple in approved_triples:
            assert triple.evidence_quote.lower() in pdf_content.lower()
```

### Property 2: SHACL Compliance
**Description**: All approved triples must pass SHACL validation.
**Type**: Invariant property
**Test Approach**: Property-based testing with SHACL validation
**Implementation**:
```python
def test_shacl_compliance():
    """Property: All approved triples pass SHACL validation."""
    for triple in generate_triples():
        if approve_triple(triple):
            validation_result = shacl_validator.validate(triple)
            assert validation_result.is_valid
```

### Property 3: Provenance Chain
**Description**: Provenance metadata must form a complete chain from source to approved triple.
**Type**: Round-trip property
**Test Approach**: End-to-end testing of extraction pipeline
**Implementation**:
```python
def test_provenance_chain():
    """Property: Provenance forms complete chain from PDF to approved triple."""
    pdf_path = "sample.pdf"
    result = process_pdf(pdf_path)
    for triple in result.approved_triples:
        assert triple.provenance.source_document == pdf_path
        assert triple.provenance.chunk_id in result.chunk_ids
        assert triple.provenance.approved_by is not None
```

### Property 4: Entity Anchoring
**Description**: Extracted triples should be anchored to verified entities when possible.
**Type**: Metamorphic property
**Test Approach**: Compare extraction with and without entity anchoring
**Implementation**:
```python
def test_entity_anchoring():
    """Property: Entity anchoring reduces hallucinated triples."""
    chunk = DocumentChunk(content="Bank of America reported $10 billion profit")
    entities = extract_entities(chunk)  # ["Bank of America", "$10 billion"]
    
    triples_with = extract_triples_with_anchors(chunk, entities)
    triples_without = extract_triples_without_anchors(chunk)
    
    assert count_valid_triples(triples_with) >= count_valid_triples(triples_without)
```

### Property 5: URI Normalization
**Description**: Plain-text entity names must be normalized to valid URIs with preserved labels.
**Type**: Invariant property
**Test Approach**: Test normalization of various entity formats
**Implementation**:
```python
def test_uri_normalization():
    """Property: All plain-text entities are normalized to valid chimera: URIs."""
    test_cases = [
        ("Bank of America", "chimera:Bank_of_America"),
        ("Basel III", "chimera:Basel_III"),
        ("Risk-Weighted Assets", "chimera:Risk_Weighted_Assets"),
        ("AI/ML", "chimera:AI_ML"),
    ]
    
    for original, expected in test_cases:
        uri = provenance_manager.normalize_to_uri(original)
        assert uri == expected
        # Verify rdfs:label triple is created
        label_triple = provenance_manager.create_label_triple(uri, original)
        assert label_triple[1] == "rdfs:label"
        assert f'"{original}"' in label_triple[2]
```

### Property 6: Live Reload Functionality
**Description**: Newly approved triples must be immediately queryable without restart.
**Type**: Round-trip property
**Test Approach**: Integration test of approval and query flow
**Implementation**:
```python
def test_live_reload():
    """Property: Approved triples are immediately queryable."""
    # Initial state
    initial_count = len(graph_store.query("SELECT * WHERE { ?s ?p ?o }"))
    
    # Approve a triple
    staging_manager.approve_triple("triple_123", "test_user")
    
    # Immediate query should include new triple
    new_count = len(graph_store.query("SELECT * WHERE { ?s ?p ?o }"))
    assert new_count == initial_count + 1  # Plus additional provenance triples
    
    # Verify the specific triple is queryable
    result = graph_store.query(f"ASK {{ chimera:Bank_of_America ?p ?o }}")
    assert result is True
```

## Error Handling

### 1. PDF Parsing Errors
- **Corrupted PDF files**: Provide clear error message, continue processing other documents
- **Password-protected PDFs**: Inform user and skip processing
- **Large PDF files**: Implement streaming parsing with progress indicators

### 2. LLM Extraction Errors
- **Ollama service unavailable**: Queue extraction tasks with exponential backoff retry
- **JSON parsing failures**: Log error, skip malformed extraction, continue with other chunks
- **Timeout during extraction**: Implement configurable timeouts with retry logic

### 3. SHACL Validation Errors
- **Malformed triples**: Quarantine with detailed error explanations
- **Missing ontology classes**: Use fallback predicates with warnings
- **Shape validation failures**: Tag as QUARANTINED with specific error messages

### 4. Staging Manager Errors
- **Corrupted staging file**: Create backup and initialize new staging area
- **Concurrent modifications**: Implement transaction semantics with rollback
- **Disk space issues**: Monitor storage and provide early warnings

### 5. Streamlit UI Errors
- **File upload failures**: Clear error messages with resolution steps
- **Session timeouts**: Graceful reconnection with state preservation
- **Visualization failures**: Fallback to tabular display with error logging

### 6. Pipeline Orchestration Errors
- **Component initialization failures**: Graceful degradation with clear error reporting
- **Evidence grounding failures**: Automatic filtering with user notification
- **Vector store insertion failures**: Retry logic with batch processing
- **Live reload failures**: Fallback to manual refresh with user guidance

### 7. Recovery Mechanisms
- **Checkpointing**: Save intermediate state during long PDF processing
- **Transaction logs**: Maintain audit trail for recovery operations
- **Health monitoring**: Proactive detection and recovery of component failures

## Testing Strategy

### 1. Unit Tests
- **PDF Parser**: Test parsing of various PDF formats and chunking logic
- **Entity Extractor**: Test spaCy entity extraction and filtering
- **Triple Extractor**: Test LLM integration and evidence verification
- **SHACL Validator**: Test validation logic against various triple structures
- **Staging Manager**: Test approval workflow and data persistence
- **Ingestion Pipeline**: Test orchestration logic and error handling
- **Provenance Manager**: Test URI normalization and label creation

### 2. Integration Tests
- **End-to-end pipeline**: Complete PDF ingestion from upload to approval
- **Component interactions**: Test interfaces between all engine components
- **Streamlit integration**: Test UI components with backend services
- **Docker deployment**: Test container build and runtime behavior
- **Live reload workflow**: Test approval and immediate queryability

### 3. Property-Based Tests
- **Evidence grounding**: All approved triples have valid evidence quotes
- **SHACL compliance**: All approved triples pass validation
- **Provenance integrity**: Complete chain from source to approved triple
- **Entity anchoring**: Entity-based extraction reduces hallucinations
- **URI normalization**: Consistent transformation to valid URIs
- **Live reload**: Approved triples immediately available for query

### 4. Performance Tests
- **PDF processing time**: Measure vs document size and complexity
- **Memory usage**: Profile during large document processing
- **Concurrent operations**: Test multiple users and simultaneous uploads
- **Ollama performance**: Monitor response times under load
- **Live reload latency**: Measure time from approval to query availability

### 5. Security Tests
- **Input validation**: Test with malicious PDF files and content
- **Access controls**: Verify proper isolation between users/sessions
- **Data protection**: Ensure sensitive data doesn't leave container
- **Audit logging**: Verify comprehensive operation tracking

### 6. Compliance Tests
- **HKMA GenAI Sandbox**: Verify air-gapped operation and deterministic guardrails
- **ART Framework**: Test accountability and transparency features
- **Provenance tracking**: Validate complete audit trail functionality
- **Human-in-the-loop**: Verify manual approval requirements

## Kiro Integration

### 1. Spec-Driven Development
- This design document as implementation reference
- Task breakdown linked to design components
- Progress tracking through spec updates

### 2. Steering Compliance
- Adherence to `coding_standards.md` for all new code
- Following `project_guidelines.md` architectural patterns
- Alignment with `kiro_workflow.md` development procedures

### 3. Hook Integration
- Extend `validate-ontology.json` for new SHACL shapes
- Update `run-tests.json` to include new test modules
- Ensure `lint-code.json` passes on all new files

### 4. AI-Assisted Development
- Kiro for code generation from design specifications
- AI review of implementation against requirements
- Automated documentation updates

## Conclusion

This design provides a comprehensive architecture for extending The Alchemist's Chimera with dynamic PDF-to-RDF ingestion capabilities while maintaining regulatory compliance, performance, and integration with existing Kiro workflows. The system embodies the "Frankenstein" theme by stitching together semantic web technologies with modern neural RAG components through a controlled "Surgeon's Table" workflow.

Key enhancements in this updated design include:

1. **IngestionPipeline Orchestrator**: Coordinates all 5 ingestor components, performs verbatim evidence quote substring grounding checks, inserts document chunks into the existing VectorStore for hybrid retrieval, and manages the flow of validated/quarantined triples to the StagingManager.

2. **URI Normalization in ProvenanceManager**: Normalizes plain-text entity names into valid `chimera:` URIs while preserving the original text as `rdfs:label` triples, ensuring RDFLib and pyshacl never fail on spaces or special characters.

3. **Live Reload in StagingManager**: The `approve_triple()` method triggers a live reload on the active GraphStore instance, making newly approved triples immediately queryable in the Hybrid Chat tab without restarting Streamlit.

These implementation details ensure a seamless user experience where extracted knowledge becomes available immediately upon approval, maintaining the system's deterministic guardrails while providing real-time feedback and integration with existing hybrid retrieval components.

### Practical Constraints for Hugging Face Spaces Deployment

To ensure reliable operation on Hugging Face Spaces free-tier for Kiroween judging, the following practical constraints are implemented:

1. **No Login Wall**: For Devpost judges on Hugging Face Spaces, the system uses a sidebar role selector instead of a password/login gate, with options like "Compliance Officer (Demo)" and "Risk Auditor" to tag HITL approvals in the audit trail.

2. **Sequential Ollama Inference**: Ollama qwen2.5:3b extraction runs sequentially (one chunk at a time) rather than in parallel to stay within Hugging Face Spaces' 2 vCPU / 16 GB RAM free-tier limits.

3. **Hugging Face Non-Root Permissions**: Hugging Face Spaces runs containers as UID 1000, so the Docker configuration sets ENV OLLAMA_MODELS=/app/.ollama/models, ENV HF_HOME=/app/.cache, and ensures proper permissions to prevent PermissionDenied errors for Ollama, sentence-transformers, and ChromaDB.

These constraints ensure the system works reliably on Hugging Face Spaces free-tier infrastructure while maintaining the full functionality required for Kiroween evaluation.
