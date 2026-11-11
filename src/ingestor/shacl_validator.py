"""
SHACL Validator for Alchemist's Chimera.

Validates extracted triples against SHACL (Shapes Constraint Language) constraints
to ensure data quality and compliance with ontology requirements.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import tempfile
import json

# Try to import pyshacl, but provide fallback if not available
try:
    import pyshacl
    PYSHACL_AVAILABLE = True
except ImportError:
    PYSHACL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("pyshacl not available, using fallback validation")

# Local imports
from .triple_extractor import ExtractedTriple
from .provenance_manager import ProvenanceManager
from ..config import settings

logger = logging.getLogger(__name__)


class ValidationResult:
    """Result of SHACL validation."""
    
    def __init__(self, is_valid: bool, messages: List[str], report: Optional[Dict[str, Any]] = None):
        self.is_valid = is_valid
        self.messages = messages
        self.report = report or {}
    
    def __bool__(self):
        return self.is_valid


class SHACLValidator:
    """Validates triples against SHACL shapes."""
    
    def __init__(self, shapes_file: Optional[Path] = None, base_uri: str = "http://alchemists-chimera.org/"):
        """Initialize SHACL validator.
        
        Args:
            shapes_file: Path to SHACL shapes file (.ttl format)
            base_uri: Base URI for namespace generation
        """
        self.shapes_file = shapes_file
        self.base_uri = base_uri
        
        if not PYSHACL_AVAILABLE:
            logger.warning("pyshacl not installed, using basic validation only")
            logger.info("To enable full SHACL validation, install with: pip install pyshacl")
        
        # Default shape constraints (basic validation)
        self.default_shapes = self._generate_default_shapes()
        
        logger.info(f"SHACL validator initialized with shapes: {self.shapes_file}")
        logger.info(f"Full SHACL support: {PYSHACL_AVAILABLE}")
    
    def _generate_default_shapes(self) -> str:
        """Generate default SHACL shapes for basic validation.
        
        Returns:
            Turtle string with default shapes
        """
        return f"""
@prefix chimera: <{self.base_uri}> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# Default shape for all triples
chimera:TripleShape
    a sh:NodeShape ;
    sh:targetClass chimera:ExtractedTriple ;
    sh:property [
        sh:path chimera:subject ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:message "Subject is required and must be a string" ;
    ] ;
    sh:property [
        sh:path chimera:predicate ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:message "Predicate is required and must be a string" ;
    ] ;
    sh:property [
        sh:path chimera:object ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:datatype xsd:string ;
        sh:message "Object is required and must be a string" ;
    ] ;
    sh:property [
        sh:path chimera:confidence ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 1.0 ;
        sh:datatype xsd:float ;
        sh:message "Confidence must be between 0 and 1" ;
    ] ;
    sh:property [
        sh:path chimera:evidence ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
        sh:minLength 10 ;
        sh:message "Evidence is required and must be at least 10 characters" ;
    ] .
    
# Shape for low confidence triples (quarantine)
chimera:LowConfidenceShape
    a sh:NodeShape ;
    sh:targetObjectsOf chimera:hasConfidence ;
    sh:lessThan 0.3 ;
    sh:severity sh:Warning ;
    sh:message "Low confidence (<0.3), recommended for quarantine" ;
    .
    
# Shape for short evidence (quarantine)
chimera:ShortEvidenceShape
    a sh:NodeShape ;
    sh:targetObjectsOf chimera:hasEvidence ;
    sh:maxLength 20 ;
    sh:severity sh:Warning ;
    sh:message "Evidence too short (<20 chars), recommended for quarantine" ;
    .
"""
    
    def validate_triple(self, triple: ExtractedTriple) -> Tuple[bool, List[str]]:
        """Validate a single extracted triple.
        
        Args:
            triple: Extracted triple to validate
            
        Returns:
            Tuple of (is_valid, validation_messages)
        """
        messages = []
        
        # Basic validation (always available)
        basic_valid, basic_messages = self._basic_validation(triple)
        messages.extend(basic_messages)
        
        # Full SHACL validation if available
        if PYSHACL_AVAILABLE:
            shacl_valid, shacl_messages = self._shacl_validation([triple])
            messages.extend(shacl_messages)
            is_valid = basic_valid and shacl_valid
        else:
            is_valid = basic_valid
        
        # Add summary message
        if is_valid:
            messages.append("Triple passes all validation checks")
        else:
            messages.append("Triple failed one or more validation checks")
        
        logger.debug(f"Validated triple {triple.subject} {triple.predicate} {triple.object}: "
                    f"{'VALID' if is_valid else 'INVALID'} ({len(messages)} messages)")
        
        return is_valid, messages
    
    def _basic_validation(self, triple: ExtractedTriple) -> Tuple[bool, List[str]]:
        """Perform basic validation (always available).
        
        Args:
            triple: Extracted triple to validate
            
        Returns:
            Tuple of (is_valid, messages)
        """
        messages = []
        issues = []
        
        # Check required fields
        if not triple.subject or not triple.subject.strip():
            issues.append("Missing or empty subject")
        
        if not triple.predicate or not triple.predicate.strip():
            issues.append("Missing or empty predicate")
        
        if not triple.object or not triple.object.strip():
            issues.append("Missing or empty object")
        
        # Check confidence range
        if not 0.0 <= triple.confidence <= 1.0:
            issues.append(f"Confidence {triple.confidence} out of range [0, 1]")
        
        # Check evidence
        if not triple.evidence or not triple.evidence.strip():
            issues.append("Missing evidence")
        elif len(triple.evidence) < 10:
            issues.append(f"Evidence too short ({len(triple.evidence)} chars, minimum 10)")
        
        # Check for reasonable entity prefixes
        if triple.subject and ':' not in triple.subject and not triple.subject.startswith('http'):
            messages.append(f"Subject missing namespace prefix: {triple.subject}")
        
        if triple.predicate and ':' not in triple.predicate and not triple.predicate.startswith('http'):
            messages.append(f"Predicate missing namespace prefix: {triple.predicate}")
        
        # Determine validity
        is_valid = len(issues) == 0
        
        # Convert issues to messages
        all_messages = []
        if issues:
            all_messages.append("Validation issues found:")
            all_messages.extend([f"  - {issue}" for issue in issues])
        else:
            all_messages.append("Basic validation passed")
        
        # Add informational messages
        all_messages.extend(messages)
        
        return is_valid, all_messages
    
    def _shacl_validation(self, triples: List[ExtractedTriple]) -> Tuple[bool, List[str]]:
        """Perform full SHACL validation (requires pyshacl).
        
        Args:
            triples: List of extracted triples
            
        Returns:
            Tuple of (is_valid, messages)
        """
        if not PYSHACL_AVAILABLE:
            return True, ["SHACL validation not available (pyshacl not installed)"]
        
        try:
            # Convert triples to RDF graph
            data_graph = self._triples_to_rdf(triples)
            
            # Get shapes graph
            shapes_graph = self._get_shapes_graph()
            
            # Run SHACL validation
            conforms, results_graph, results_text = pyshacl.validate(
                data_graph=data_graph,
                shacl_graph=shapes_graph,
                inference='rdfs',
                abort_on_first=False,
                meta_shacl=False,
                debug=False,
            )
            
            # Parse results
            messages = self._parse_shacl_results(results_graph, conforms)
            
            logger.info(f"SHACL validation completed: {'CONFORMS' if conforms else 'VIOLATIONS FOUND'}")
            return conforms, messages
            
        except Exception as e:
            logger.error(f"SHACL validation failed: {e}")
            return False, [f"SHACL validation error: {str(e)}"]
    
    def _triples_to_rdf(self, triples: List[ExtractedTriple]) -> str:
        """Convert triples to RDF graph in Turtle format.
        
        Args:
            triples: List of extracted triples
            
        Returns:
            Turtle string with triples
        """
        from rdflib import Graph, Namespace, URIRef, Literal, RDF
        from rdflib.namespace import RDF, RDFS, XSD
        
        graph = Graph()
        
        # Define namespaces
        CHIMERA = Namespace(self.base_uri)
        graph.bind("chimera", CHIMERA)
        graph.bind("rdf", RDF)
        graph.bind("rdfs", RDFS)
        graph.bind("xsd", XSD)
        
        for i, triple in enumerate(triples):
            # Create unique URI for this triple
            triple_uri = URIRef(f"{self.base_uri}triple/{triple.chunk_id}_{i}")
            
            # Add triple metadata
            graph.add((triple_uri, RDF.type, CHIMERA.ExtractedTriple))
            graph.add((triple_uri, CHIMERA.subject, Literal(triple.subject, datatype=XSD.string)))
            graph.add((triple_uri, CHIMERA.predicate, Literal(triple.predicate, datatype=XSD.string)))
            graph.add((triple_uri, CHIMERA.object, Literal(triple.object, datatype=XSD.string)))
            graph.add((triple_uri, CHIMERA.evidence, Literal(triple.evidence, datatype=XSD.string)))
            graph.add((triple_uri, CHIMERA.confidence, Literal(triple.confidence, datatype=XSD.float)))
            graph.add((triple_uri, CHIMERA.chunk_id, Literal(triple.chunk_id, datatype=XSD.string)))
            
            # Add entity anchors if available
            if hasattr(triple, 'entity_anchors') and triple.entity_anchors:
                for anchor in triple.entity_anchors:
                    graph.add((triple_uri, CHIMERA.entityAnchor, Literal(anchor, datatype=XSD.string)))
        
        return graph.serialize(format='turtle')
    
    def _get_shapes_graph(self) -> str:
        """Get SHACL shapes graph.
        
        Returns:
            Shapes graph in Turtle format
        """
        if self.shapes_file and self.shapes_file.exists():
            with open(self.shapes_file, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return self.default_shapes
    
    def _parse_shacl_results(self, results_graph, conforms: bool) -> List[str]:
        """Parse SHACL validation results.
        
        Args:
            results_graph: SHACL results graph
            conforms: Whether data conforms to shapes
            
        Returns:
            List of validation messages
        """
        messages = []
        
        if conforms:
            messages.append("Data conforms to SHACL shapes")
            return messages
        
        # Parse violation details from results graph
        try:
            from rdflib import Graph
            from rdflib.namespace import SH
            
            # Convert to graph if it's a string
            if isinstance(results_graph, str):
                g = Graph()
                g.parse(data=results_graph, format='turtle')
            else:
                g = results_graph
            
            # Query for validation results
            query = """
            SELECT ?focusNode ?resultMessage ?resultSeverity ?sourceConstraintComponent
            WHERE {
                ?result a sh:ValidationResult ;
                        sh:focusNode ?focusNode ;
                        sh:resultMessage ?resultMessage ;
                        sh:resultSeverity ?resultSeverity .
                OPTIONAL { ?result sh:sourceConstraintComponent ?sourceConstraintComponent }
            }
            """
            
            results = g.query(query)
            
            for row in results:
                focus_node = str(row[0])
                message = str(row[1])
                severity = str(row[2])
                constraint = str(row[3]) if row[3] else "unknown"
                
                msg = f"{severity}: {message} (constraint: {constraint}, focus: {focus_node})"
                messages.append(msg)
                
        except Exception as e:
            logger.error(f"Failed to parse SHACL results: {e}")
            messages.append(f"Could not parse detailed validation results: {e}")
        
        if not messages:
            messages.append("Data does not conform to SHACL shapes (no detailed results available)")
        
        return messages
    
    def batch_validate(self, triples: List[ExtractedTriple]) -> Dict[str, Tuple[bool, List[str]]]:
        """Batch validate multiple triples.
        
        Args:
            triples: List of extracted triples
            
        Returns:
            Dictionary mapping triple ID to (is_valid, messages)
        """
        results = {}
        
        if PYSHACL_AVAILABLE:
            # Use SHACL for batch validation
            is_valid, messages = self._shacl_validation(triples)
            
            # All triples get the same result from batch validation
            for triple in triples:
                triple_id = triple.chunk_id + "_" + str(id(triple))
                results[triple_id] = (is_valid, messages)
        else:
            # Fall back to individual basic validation
            for triple in triples:
                is_valid, messages = self._basic_validation(triple)
                triple_id = triple.chunk_id + "_" + str(id(triple))
                results[triple_id] = (is_valid, messages)
        
        return results
    
    def validate_and_classify(self, triple: ExtractedTriple) -> Tuple[str, List[str]]:
        """Validate triple and classify result (valid, quarantine, invalid).
        
        Args:
            triple: Extracted triple to validate
            
        Returns:
            Tuple of (classification, messages)
        """
        is_valid, messages = self.validate_triple(triple)
        
        if not is_valid:
            return "invalid", messages
        
        # Check for quarantine conditions
        quarantine_conditions = []
        
        # Low confidence
        if triple.confidence < 0.3:
            quarantine_conditions.append(f"Low confidence ({triple.confidence:.2f} < 0.3)")
        
        # Short evidence
        if len(triple.evidence) < 20:
            quarantine_conditions.append(f"Short evidence ({len(triple.evidence)} chars < 20)")
        
        # Missing entity anchors
        if hasattr(triple, 'entity_anchors') and not triple.entity_anchors:
            quarantine_conditions.append("No entity anchors")
        
        if quarantine_conditions:
            quarantine_msg = "Triple valid but quarantined due to: " + "; ".join(quarantine_conditions)
            messages.append(quarantine_msg)
            return "quarantined", messages
        
        return "valid", messages
    
    def create_validation_report(self, triples: List[ExtractedTriple]) -> Dict[str, Any]:
        """Create a comprehensive validation report.
        
        Args:
            triples: List of extracted triples
            
        Returns:
            Dictionary with validation report
        """
        classifications = {
            "valid": 0,
            "quarantined": 0,
            "invalid": 0,
        }
        
        all_messages = []
        batch_results = self.batch_validate(triples)
        
        for triple in triples:
            triple_id = triple.chunk_id + "_" + str(id(triple))
            is_valid, messages = batch_results.get(triple_id, (False, ["Validation failed"]))
            
            if not is_valid:
                classifications["invalid"] += 1
                all_messages.append(f"INVALID: {triple.subject} {triple.predicate} {triple.object}")
                all_messages.extend([f"  - {msg}" for msg in messages])
            else:
                # Check for quarantine conditions
                if triple.confidence < 0.3 or len(triple.evidence) < 20:
                    classifications["quarantined"] += 1
                    all_messages.append(f"QUARANTINED: {triple.subject} {triple.predicate} {triple.object}")
                else:
                    classifications["valid"] += 1
                    all_messages.append(f"VALID: {triple.subject} {triple.predicate} {triple.object}")
        
        return {
            "total_triples": len(triples),
            "classifications": classifications,
            "validation_rate": classifications["valid"] / len(triples) if triples else 0,
            "quarantine_rate": classifications["quarantined"] / len(triples) if triples else 0,
            "invalid_rate": classifications["invalid"] / len(triples) if triples else 0,
            "messages": all_messages,
            "shapes_used": "default" if not self.shapes_file else str(self.shapes_file),
            "pyshacl_available": PYSHACL_AVAILABLE,
        }


def main():
    """Example usage and testing of SHACL validator."""
    import sys
    from datetime import datetime
    
    print("Testing SHACL Validator...")
    print("=" * 60)
    
    # Create test triples
    test_triples = [
        ExtractedTriple(
            subject="chimera:Basel_Committee",
            predicate="chimera:develops",
            object="chimera:Basel_III_framework",
            evidence="The Basel III framework was developed by the Basel Committee on Banking Supervision.",
            confidence=0.95,
            chunk_id="test-chunk-001",
            entity_anchors=["Basel Committee", "Basel III"],
            metadata={},
            extraction_timestamp=datetime.now()
        ),
        ExtractedTriple(
            subject="",  # Invalid: empty subject
            predicate="chimera:requires",
            object="Capital requirements",
            evidence="Banks must meet requirements",
            confidence=0.8,
            chunk_id="test-chunk-002",
            entity_anchors=[],
            metadata={},
            extraction_timestamp=datetime.now()
        ),
        ExtractedTriple(
            subject="HKMA",
            predicate="chimera:implements",
            object="Regulations",
            evidence="Implements",  # Too short
            confidence=0.2,  # Low confidence
            chunk_id="test-chunk-003",
            entity_anchors=["HKMA"],
            metadata={},
            extraction_timestamp=datetime.now()
        ),
    ]
    
    try:
        # Create validator
        validator = SHACLValidator()
        
        # Test individual validation
        print("\nTesting individual triple validation:")
        for i, triple in enumerate(test_triples, 1):
            print(f"\nTriple {i}: {triple.subject} {triple.predicate} {triple.object}")
            classification, messages = validator.validate_and_classify(triple)
            print(f"Classification: {classification.upper()}")
            for msg in messages[:3]:  # Show first 3 messages
                print(f"  {msg}")
        
        # Test batch validation
        print("\n" + "=" * 60)
        print("Testing batch validation...")
        
        report = validator.create_validation_report(test_triples)
        
        print(f"\nValidation Report:")
        print(f"Total triples: {report['total_triples']}")
        print(f"Valid: {report['classifications']['valid']}")
        print(f"Quarantined: {report['classifications']['quarantined']}")
        print(f"Invalid: {report['classifications']['invalid']}")
        print(f"Validation rate: {report['validation_rate']:.1%}")
        print(f"Quarantine rate: {report['quarantine_rate']:.1%}")
        print(f"Invalid rate: {report['invalid_rate']:.1%}")
        print(f"SHACL available: {report['pyshacl_available']}")
        
        # Test with custom shapes file
        print("\n" + "=" * 60)
        print("Testing with default shapes...")
        
        # Write default shapes to file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ttl', delete=False) as f:
            f.write(validator.default_shapes)
            shapes_path = f.name
        
        try:
            validator_with_shapes = SHACLValidator(Path(shapes_path))
            print(f"Loaded shapes from: {shapes_path}")
            
            # Test validation
            is_valid, messages = validator_with_shapes.validate_triple(test_triples[0])
            print(f"\nFirst triple validation: {'VALID' if is_valid else 'INVALID'}")
            for msg in messages[:2]:
                print(f"  {msg}")
                
        finally:
            # Clean up temp file
            import os
            os.unlink(shapes_path)
        
        print("\n✅ SHACL validator test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

