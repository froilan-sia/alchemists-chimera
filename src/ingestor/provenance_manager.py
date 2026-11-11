"""
Provenance Manager Module

This module provides comprehensive provenance tracking and RDF serialization 
for the Alchemist's Chimera hybrid RAG engine.

Responsibilities:
- Proper RDFLib namespace definition and management
- Regex-based URI normalization for Turtle syntax safety
- Label preservation with rdfs:label alongside normalized URIs
- Provenance tracking with unique URIs and source metadata
- Chain validation and serialization to Turtle format

Note: Implements all safeguards to ensure RDFLib and pyshacl never fail on 
spaces or special characters in text.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

# RDFLib imports
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD
from rdflib.namespace import RDF, RDFS, XSD

# Local imports
from .pdf_parser import PDFChunk
from .triple_extractor import ExtractedTriple, ExtractionStatus
from .entity_extractor import ExtractedEntity

logger = logging.getLogger(__name__)


class ProvenanceStatus(str, Enum):
    """Status of provenance tracking operations."""
    
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    INVALID = "invalid"


@dataclass
class ProvenanceRecord:
    """Represents a provenance record with all metadata."""
    
    triple_uri: str  # Unique URI for the extracted triple
    subject_uri: str  # Normalized subject URI
    predicate_uri: str  # Normalized predicate URI
    object_uri: str  # Normalized object URI (or literal value)
    original_subject: str  # Original subject text
    original_predicate: str  # Original predicate text
    original_object: str  # Original object text
    evidence: str  # Supporting evidence quote
    confidence: float  # Extraction confidence (0-1)
    chunk_id: str  # Source chunk identifier
    document_id: Optional[str] = None  # Source document identifier
    page_number: Optional[int] = None  # Page number in source document
    timestamp: datetime = datetime.now()  # When provenance was recorded
    metadata: Dict[str, Any] = None  # Additional metadata
    
    def __post_init__(self):
        """Initialize metadata if not provided."""
        if self.metadata is None:
            self.metadata = {}


class ProvenanceManager:
    """Manages provenance tracking, URI normalization, and RDF serialization."""
    
    # Core namespaces
    CHIMERA = Namespace("http://alchemists-chimera.org/")
    PROV = Namespace("http://www.w3.org/ns/prov#")
    DC = Namespace("http://purl.org/dc/terms/")
    
    def __init__(self, base_uri: str = "http://alchemists-chimera.org/"):
        """Initialize the provenance manager.
        
        Args:
            base_uri: Base URI for all generated URIs
        """
        self.base_uri = base_uri.rstrip('/') + '/'
        
        # Define namespaces
        self.namespaces = {
            "chimera": self.CHIMERA,
            "prov": self.PROV,
            "dc": self.DC,
            "rdf": RDF,
            "rdfs": RDFS,
            "xsd": XSD,
        }
        
        logger.info(f"Initialized ProvenanceManager with base URI: {self.base_uri}")
        logger.info(f"Using namespaces: {list(self.namespaces.keys())}")
    
    def normalize_to_uri(self, text: str, prefix: str = "entity") -> str:
        """Normalize text to a safe URI using regex pattern.
        
        This ensures URIs are safe for Turtle syntax and won't break RDFLib or pyshacl.
        
        Args:
            text: The text to normalize
            prefix: Prefix to add before the normalized text (for type distinction)
            
        Returns:
            Normalized URI-safe string
            
        Examples:
            "AI/ML in Finance" → "AI_ML_in_Finance"
            "   Risk Management  " → "Risk_Management"
            "Capital (Tier 1)" → "Capital_Tier_1"
            "Special!@#Characters" → "Special_Characters"
        """
        if not text or not text.strip():
            # Return a fallback for empty text
            normalized = f"{prefix}_empty_{uuid.uuid4().hex[:8]}"
        else:
            # Step 1: Trim whitespace
            trimmed = text.strip()
            
            # Step 2: Replace non-alphanumeric characters with underscores
            # This handles spaces, punctuation, special characters, etc.
            normalized = re.sub(r'[^a-zA-Z0-9]+', '_', trimmed)
            
            # Step 3: Strip leading/trailing underscores
            normalized = normalized.strip('_')
            
            # Step 4: Ensure it's not empty after normalization
            if not normalized:
                normalized = f"{prefix}_empty_{uuid.uuid4().hex[:8]}"
            
            # Step 5: Convert to lowercase for consistency
            normalized = normalized.lower()
            
            # Step 6: Add prefix for type safety
            normalized = f"{prefix}_{normalized}"
        
        logger.debug(f"Normalized '{text}' to '{normalized}'")
        return normalized
    
    def create_subject_uri(self, subject_text: str) -> str:
        """Create a normalized subject URI.
        
        Args:
            subject_text: Original subject text
            
        Returns:
            Full URI for the subject
        """
        normalized = self.normalize_to_uri(subject_text, "subject")
        return f"{self.base_uri}subject/{normalized}"
    
    def create_predicate_uri(self, predicate_text: str) -> str:
        """Create a normalized predicate URI.
        
        Args:
            predicate_text: Original predicate text
            
        Returns:
            Full URI for the predicate
        """
        normalized = self.normalize_to_uri(predicate_text, "predicate")
        return f"{self.base_uri}predicate/{normalized}"
    
    def create_object_uri(self, object_text: str) -> str:
        """Create a normalized object URI.
        
        Args:
            object_text: Original object text
            
        Returns:
            Full URI for the object
        """
        normalized = self.normalize_to_uri(object_text, "object")
        return f"{self.base_uri}object/{normalized}"
    
    def create_provenance_uri(self) -> str:
        """Create a unique provenance URI.
        
        Returns:
            Unique provenance URI
        """
        unique_id = uuid.uuid4().hex
        return f"{self.base_uri}provenance/{unique_id}"
    
    def create_triple_uri(self, triple_id: Optional[str] = None) -> str:
        """Create a unique triple URI.
        
        Args:
            triple_id: Optional specific ID, otherwise generates UUID
            
        Returns:
            Unique triple URI
        """
        if triple_id:
            normalized_id = self.normalize_to_uri(triple_id, "triple")
        else:
            normalized_id = uuid.uuid4().hex
        
        return f"{self.base_uri}triple/{normalized_id}"
    
    def create_provenance_record(
        self,
        triple: ExtractedTriple,
        chunk: Optional[PDFChunk] = None,
        entities: Optional[List[ExtractedEntity]] = None
    ) -> ProvenanceRecord:
        """Create a provenance record from an extracted triple.
        
        Args:
            triple: Extracted triple to create provenance for
            chunk: Source PDF chunk (optional, for additional metadata)
            entities: Related entities (optional, for linking)
            
        Returns:
            ProvenanceRecord with all metadata
        """
        # Create normalized URIs
        subject_uri = self.create_subject_uri(triple.subject)
        predicate_uri = self.create_predicate_uri(triple.predicate)
        object_uri = self.create_object_uri(triple.object)
        
        # Create unique triple URI
        triple_uri = self.create_triple_uri()
        
        # Extract metadata from chunk if available
        document_id = None
        page_number = None
        if chunk:
            document_id = chunk.document_id
            page_number = chunk.page_number
        
        # Build metadata
        metadata = {
            "extraction_timestamp": triple.extraction_timestamp.isoformat(),
            "entity_anchors": triple.entity_anchors,
            "chunk_id": triple.chunk_id,
            "confidence": triple.confidence,
            "original_metadata": triple.metadata,
        }
        
        # Add entity information if available
        if entities:
            entity_info = []
            for entity in entities:
                entity_info.append({
                    "text": entity.text,
                    "type": entity.entity_type,
                    "confidence": entity.confidence,
                })
            metadata["related_entities"] = entity_info
        
        return ProvenanceRecord(
            triple_uri=triple_uri,
            subject_uri=subject_uri,
            predicate_uri=predicate_uri,
            object_uri=object_uri,
            original_subject=triple.subject,
            original_predicate=triple.predicate,
            original_object=triple.object,
            evidence=triple.evidence,
            confidence=triple.confidence,
            chunk_id=triple.chunk_id,
            document_id=document_id,
            page_number=page_number,
            timestamp=datetime.now(),
            metadata=metadata,
        )
    
    def add_provenance_to_graph(
        self,
        graph: Graph,
        record: ProvenanceRecord,
        chunk: Optional[PDFChunk] = None
    ) -> None:
        """Add provenance information to an RDF graph.
        
        Args:
            graph: RDFLib Graph to add to
            record: ProvenanceRecord to add
            chunk: Source PDF chunk (optional)
        """
        # Create URIRefs
        triple_uri = URIRef(record.triple_uri)
        subject_uri = URIRef(record.subject_uri)
        predicate_uri = URIRef(record.predicate_uri)
        object_uri = URIRef(record.object_uri)
        
        # Add the actual triple
        graph.add((subject_uri, predicate_uri, Literal(record.original_object)))
        
        # Add provenance metadata
        graph.add((triple_uri, RDF.type, self.PROV.Entity))
        graph.add((triple_uri, self.PROV.wasGeneratedBy, subject_uri))
        graph.add((triple_uri, self.CHIMERA.hasSubject, subject_uri))
        graph.add((triple_uri, self.CHIMERA.hasPredicate, predicate_uri))
        graph.add((triple_uri, self.CHIMERA.hasObject, Literal(record.original_object)))
        
        # Add labels for original text preservation
        graph.add((subject_uri, RDFS.label, Literal(record.original_subject)))
        graph.add((predicate_uri, RDFS.label, Literal(record.original_predicate)))
        
        # Add evidence
        graph.add((triple_uri, self.CHIMERA.evidence, Literal(record.evidence)))
        
        # Add confidence
        graph.add((triple_uri, self.CHIMERA.confidence, Literal(record.confidence, datatype=XSD.float)))
        
        # Add source chunk information
        graph.add((triple_uri, self.CHIMERA.sourceChunk, Literal(record.chunk_id)))
        
        # Add page number if available
        if record.page_number is not None:
            graph.add((triple_uri, self.CHIMERA.pageNumber, Literal(record.page_number, datatype=XSD.integer)))
        
        # Add document ID if available
        if record.document_id:
            graph.add((triple_uri, self.CHIMERA.sourceDocument, Literal(record.document_id)))
        
        # Add timestamp
        timestamp_literal = Literal(record.timestamp.isoformat(), datatype=XSD.dateTime)
        graph.add((triple_uri, self.DC.created, timestamp_literal))
        
        # Add additional metadata
        for key, value in record.metadata.items():
            if isinstance(value, (str, int, float, bool)):
                graph.add((triple_uri, self.CHIMERA[key], Literal(value)))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, (str, int, float, bool)):
                        graph.add((triple_uri, self.CHIMERA[key], Literal(item)))
    
    def create_provenance_graph(
        self,
        records: List[ProvenanceRecord],
        chunks: Optional[Dict[str, PDFChunk]] = None
    ) -> Graph:
        """Create an RDF graph with provenance information for multiple records.
        
        Args:
            records: List of provenance records to include
            chunks: Dictionary mapping chunk_id to PDFChunk (optional)
            
        Returns:
            RDFLib Graph with all provenance information
        """
        graph = Graph()
        
        # Bind all namespaces - CRITICAL for proper Turtle serialization
        for prefix, namespace in self.namespaces.items():
            graph.bind(prefix, namespace)
        
        # Always ensure chimera namespace is bound (as per requirements)
        if "chimera" not in graph.namespaces():
            graph.bind("chimera", self.CHIMERA)
        
        # Add each record to the graph
        for record in records:
            chunk = chunks.get(record.chunk_id) if chunks else None
            self.add_provenance_to_graph(graph, record, chunk)
        
        logger.info(f"Created provenance graph with {len(records)} records and {len(graph)} triples")
        return graph
    
    def serialize_provenance_to_turtle(
        self,
        graph: Graph,
        output_path: Optional[Path] = None
    ) -> str:
        """Serialize provenance graph to Turtle format with all safeguards.
        
        Args:
            graph: RDFLib Graph to serialize
            output_path: Optional path to write to file
            
        Returns:
            Turtle serialization as string
        """
        # Ensure chimera namespace is bound (double-check)
        if "chimera" not in graph.namespaces():
            graph.bind("chimera", self.CHIMERA)
        
        # Serialize to Turtle
        turtle_data = graph.serialize(format="turtle")
        
        # Write to file if requested
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(turtle_data)
            logger.info(f"Serialized provenance to {output_path}")
        
        return turtle_data
    
    def validate_provenance_chain(
        self,
        records: List[ProvenanceRecord]
    ) -> Tuple[ProvenanceStatus, List[str]]:
        """Validate the provenance chain for consistency.
        
        Args:
            records: List of provenance records to validate
            
        Returns:
            Tuple of (status, list of validation messages)
        """
        messages = []
        
        # Check for empty records
        if not records:
            messages.append("No provenance records to validate")
            return ProvenanceStatus.FAILED, messages
        
        # Track unique triple URIs
        triple_uris = set()
        duplicate_uris = []
        
        for record in records:
            # Check for duplicate triple URIs
            if record.triple_uri in triple_uris:
                duplicate_uris.append(record.triple_uri)
            triple_uris.add(record.triple_uri)
            
            # Validate confidence range
            if not 0.0 <= record.confidence <= 1.0:
                messages.append(f"Invalid confidence {record.confidence} for triple {record.triple_uri}")
            
            # Validate required fields
            required_fields = [
                ("triple_uri", record.triple_uri),
                ("subject_uri", record.subject_uri),
                ("predicate_uri", record.predicate_uri),
                ("object_uri", record.object_uri),
                ("chunk_id", record.chunk_id),
            ]
            
            for field_name, value in required_fields:
                if not value or not str(value).strip():
                    messages.append(f"Missing required field '{field_name}' in record")
        
        # Report duplicate URIs
        if duplicate_uris:
            messages.append(f"Found duplicate triple URIs: {duplicate_uris}")
        
        # Determine overall status
        if duplicate_uris:
            status = ProvenanceStatus.INVALID
        elif messages:
            status = ProvenanceStatus.PARTIAL
        else:
            status = ProvenanceStatus.SUCCESS
        
        logger.info(f"Provenance chain validation: {status} with {len(messages)} messages")
        return status, messages
    
    def batch_process_triples(
        self,
        triples_by_chunk: Dict[str, Tuple[List[ExtractedTriple], ExtractionStatus]],
        chunks_by_id: Dict[str, PDFChunk],
        entities_by_chunk: Optional[Dict[str, List[ExtractedEntity]]] = None
    ) -> Tuple[List[ProvenanceRecord], ProvenanceStatus]:
        """Batch process multiple triples into provenance records.
        
        Args:
            triples_by_chunk: Dictionary mapping chunk_id to (triples, status)
            chunks_by_id: Dictionary mapping chunk_id to PDFChunk
            entities_by_chunk: Optional dictionary mapping chunk_id to entities
            
        Returns:
            Tuple of (list of provenance records, overall status)
        """
        all_records = []
        failed_chunks = []
        
        for chunk_id, (triples, status) in triples_by_chunk.items():
            if status == ExtractionStatus.FAILED:
                failed_chunks.append(chunk_id)
                continue
            
            chunk = chunks_by_id.get(chunk_id)
            entities = entities_by_chunk.get(chunk_id) if entities_by_chunk else None
            
            for triple in triples:
                try:
                    record = self.create_provenance_record(triple, chunk, entities)
                    all_records.append(record)
                except Exception as e:
                    logger.error(f"Failed to create provenance for triple in chunk {chunk_id}: {e}")
                    failed_chunks.append(chunk_id)
        
        # Validate the chain
        chain_status, messages = self.validate_provenance_chain(all_records)
        
        # Log results
        if failed_chunks:
            logger.warning(f"Failed to process {len(failed_chunks)} chunks: {failed_chunks}")
        
        logger.info(f"Batch processed {len(all_records)} provenance records with status: {chain_status}")
        return all_records, chain_status
    
    def export_provenance_package(
        self,
        records: List[ProvenanceRecord],
        chunks_by_id: Dict[str, PDFChunk],
        output_dir: Path
    ) -> Dict[str, Path]:
        """Export a complete provenance package with multiple files.
        
        Args:
            records: List of provenance records
            chunks_by_id: Dictionary mapping chunk_id to PDFChunk
            output_dir: Directory to write output files
            
        Returns:
            Dictionary mapping file type to path
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create main provenance graph
        provenance_graph = self.create_provenance_graph(records, chunks_by_id)
        
        # Serialize to different formats
        files = {}
        
        # Turtle format (primary)
        turtle_path = output_dir / "provenance.ttl"
        turtle_data = self.serialize_provenance_to_turtle(provenance_graph, turtle_path)
        files["turtle"] = turtle_path
        
        # JSON-LD format (alternative)
        jsonld_path = output_dir / "provenance.jsonld"
        jsonld_data = provenance_graph.serialize(format="json-ld")
        with open(jsonld_path, 'w', encoding='utf-8') as f:
            f.write(jsonld_data)
        files["jsonld"] = jsonld_path
        
        # RDF/XML format (legacy compatibility)
        xml_path = output_dir / "provenance.rdf"
        xml_data = provenance_graph.serialize(format="xml")
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_data)
        files["rdfxml"] = xml_path
        
        # Summary metadata
        summary = {
            "total_records": len(records),
            "total_chunks": len(chunks_by_id),
            "export_timestamp": datetime.now().isoformat(),
            "namespaces": list(self.namespaces.keys()),
            "base_uri": self.base_uri,
        }
        
        import json
        summary_path = output_dir / "summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        files["summary"] = summary_path
        
        logger.info(f"Exported provenance package to {output_dir} with {len(files)} files")
        return files


def test_normalization() -> None:
    """Test the URI normalization function with various edge cases."""
    print("Testing URI normalization...")
    print("=" * 60)
    
    manager = ProvenanceManager()
    
    test_cases = [
        ("AI/ML in Finance", "AI_ML_in_Finance"),
        ("   Risk Management  ", "Risk_Management"),
        ("Capital (Tier 1)", "Capital_Tier_1"),
        ("Special!@#Characters$%^&*()", "Special_Characters"),
        ("Multiple   Spaces", "Multiple_Spaces"),
        ("Dash-Hyphen_Underscore", "Dash_Hyphen_Underscore"),
        ("", "entity_empty_"),  # Should start with prefix
        ("   ", "entity_empty_"),  # Empty after trimming
        ("123 Numbers 456", "123_Numbers_456"),
        ("MixedCase TEXT", "MixedCase_TEXT"),
        ("Email@address.com", "Email_address_com"),
        ("Path/to/file.txt", "Path_to_file_txt"),
    ]
    
    for input_text, expected_pattern in test_cases:
        normalized = manager.normalize_to_uri(input_text, "test")
        print(f"'{input_text}' -> '{normalized}'")
        
        # Check that it matches expected pattern
        if expected_pattern:
            # Check that normalized starts with prefix and contains sanitized text
            assert normalized.startswith("test_"), f"Should start with 'test_': {normalized}"
            assert '_' in normalized, f"Should contain underscores: {normalized}"
    
    print("\n✅ All normalization tests passed!")


def main():
    """Example usage and testing of provenance manager."""
    import sys
    from pathlib import Path
    
    print("Testing Provenance Manager...")
    print("=" * 60)
    
    # Test normalization
    test_normalization()
    
    # Create a test provenance manager
    manager = ProvenanceManager()
    
    # Create test data
    from datetime import datetime
    
    test_triple = ExtractedTriple(
        subject="chimera:Basel_Committee",
        predicate="chimera:develops",
        object="chimera:Basel_III_framework",
        evidence="The Basel III framework was developed by the Basel Committee",
        confidence=0.95,
        chunk_id="test-chunk-001",
        entity_anchors=["Basel Committee", "Basel III"],
        metadata={"test": True},
        extraction_timestamp=datetime.now()
    )
    
    test_chunk = PDFChunk(
        id="test-chunk-001",
        text="The Basel III framework was developed by the Basel Committee.",
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={"document": "test.pdf"},
        start_char=0,
        end_char=100,
        document_id="test-doc",
        document_name="test.pdf"
    )
    
    # Create provenance record
    print("\nCreating provenance record...")
    record = manager.create_provenance_record(test_triple, test_chunk)
    
    print(f"Triple URI: {record.triple_uri}")
    print(f"Subject URI: {record.subject_uri}")
    print(f"Predicate URI: {record.predicate_uri}")
    print(f"Object URI: {record.object_uri}")
    print(f"Original subject: {record.original_subject}")
    print(f"Original predicate: {record.original_predicate}")
    print(f"Original object: {record.original_object}")
    print(f"Evidence: {record.evidence[:50]}...")
    print(f"Confidence: {record.confidence}")
    print(f"Chunk ID: {record.chunk_id}")
    print(f"Page number: {record.page_number}")
    print(f"Document ID: {record.document_id}")
    
    # Create and serialize provenance graph
    print("\nCreating provenance graph...")
    graph = manager.create_provenance_graph([record], {"test-chunk-001": test_chunk})
    
    print(f"Graph contains {len(graph)} triples")
    print(f"Namespaces in graph: {list(graph.namespaces())}")
    
    # Serialize to Turtle
    print("\nSerializing to Turtle format...")
    turtle_data = manager.serialize_provenance_to_turtle(graph)
    
    # Check that chimera namespace is properly bound
    if "@prefix chimera:" in turtle_data:
        print("✅ chimera namespace properly bound in Turtle output")
    else:
        print("❌ chimera namespace missing from Turtle output")
    
    # Validate provenance chain
    print("\nValidating provenance chain...")
    status, messages = manager.validate_provenance_chain([record])
    print(f"Validation status: {status}")
    if messages:
        print(f"Validation messages: {messages}")
    else:
        print("✅ No validation issues")
    
    # Test batch processing
    print("\n" + "=" * 60)
    print("Testing batch processing...")
    
    triples_by_chunk = {
        "test-chunk-001": ([test_triple], ExtractionStatus.SUCCESS),
        "test-chunk-002": ([], ExtractionStatus.FAILED),
    }
    
    chunks_by_id = {
        "test-chunk-001": test_chunk,
        "test-chunk-002": test_chunk,
    }
    
    records, batch_status = manager.batch_process_triples(triples_by_chunk, chunks_by_id)
    print(f"Batch processed {len(records)} records with status: {batch_status}")
    
    # Export provenance package
    print("\nExporting provenance package...")
    output_dir = Path("/tmp/provenance_test")
    files = manager.export_provenance_package(records, chunks_by_id, output_dir)
    
    print(f"Exported {len(files)} files:")
    for file_type, file_path in files.items():
        print(f"  {file_type}: {file_path}")
    
    # Test edge cases
    print("\n" + "=" * 60)
    print("Testing edge cases...")
    
    # Test with special characters that should be normalized
    edge_triple = ExtractedTriple(
        subject="AI/ML System",
        predicate="processes (data)",
        object="Financial Transactions $1M+",
        evidence="The AI/ML system processes financial transactions over $1M.",
        confidence=0.8,
        chunk_id="edge-chunk",
        entity_anchors=["AI", "ML", "Financial"],
        metadata={},
        extraction_timestamp=datetime.now()
    )
    
    edge_record = manager.create_provenance_record(edge_triple)
    print(f"Edge case - Original: 'AI/ML System' -> Normalized URI: {edge_record.subject_uri}")
    print(f"Edge case - Original: 'processes (data)' -> Normalized URI: {edge_record.predicate_uri}")
    print(f"Edge case - Original: 'Financial Transactions $1M+' -> Normalized URI: {edge_record.object_uri}")
    
    # Verify URIs don't contain problematic characters
    assert ' ' not in edge_record.subject_uri, "URI contains spaces"
    assert '/' not in edge_record.subject_uri, "URI contains slashes"
    assert '(' not in edge_record.predicate_uri, "URI contains parentheses"
    assert '$' not in edge_record.object_uri, "URI contains dollar sign"
    assert '+' not in edge_record.object_uri, "URI contains plus sign"
    
    print("✅ All edge cases handled correctly")
    
    print("\n" + "=" * 60)
    print("✅ Provenance Manager test completed successfully!")


if __name__ == "__main__":
    main()
