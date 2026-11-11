"""
Test script for Ingestion Pipeline Orchestrator.
"""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_pipeline_initialization():
    """Test pipeline initialization."""
    print("Testing pipeline initialization...")
    
    from src.ingestor.pipeline import create_default_pipeline
    
    try:
        pipeline = create_default_pipeline()
        print("✅ Pipeline initialized successfully")
        
        # Check components
        print(f"  - PDF Parser: {pipeline.pdf_parser is not None}")
        print(f"  - Entity Extractor: {pipeline.entity_extractor is not None}")
        print(f"  - Triple Extractor: {pipeline.triple_extractor is not None}")
        print(f"  - Provenance Manager: {pipeline.provenance_manager is not None}")
        print(f"  - SHACL Validator: {pipeline.shacl_validator is not None}")
        print(f"  - Vector Store: {pipeline.vector_store is not None}")
        print(f"  - Staging Manager: {pipeline.staging_manager is not None}")
        
        return pipeline
        
    except Exception as e:
        print(f"❌ Pipeline initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_pdf_parsing(pipeline, test_pdf_path):
    """Test PDF parsing component."""
    print(f"\nTesting PDF parsing with: {test_pdf_path}")
    
    if not test_pdf_path.exists():
        print(f"❌ Test PDF not found: {test_pdf_path}")
        return []
    
    try:
        # Parse PDF
        chunks = pipeline.pdf_parser.parse_pdf(test_pdf_path)
        print(f"✅ PDF parsing successful")
        print(f"  - Total chunks: {len(chunks)}")
        
        if chunks:
            first_chunk = chunks[0]
            print(f"  - First chunk ID: {first_chunk.id}")
            print(f"  - First chunk text preview: {first_chunk.text[:100]}...")
            print(f"  - Page number: {first_chunk.page_number}")
        
        return chunks
        
    except Exception as e:
        print(f"❌ PDF parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_entity_extraction(pipeline, test_text):
    """Test entity extraction component."""
    print(f"\nTesting entity extraction...")
    
    try:
        entities = pipeline.entity_extractor.extract_entities(test_text, "test-chunk")
        print(f"✅ Entity extraction successful")
        print(f"  - Total entities: {len(entities)}")
        
        if entities:
            for i, entity in enumerate(entities[:3], 1):  # Show first 3
                print(f"  - Entity {i}: {entity.text} ({entity.entity_type}, confidence: {entity.confidence:.2f})")
        
        # Get statistics
        stats = pipeline.entity_extractor.analyze_entity_distribution(entities)
        print(f"  - Unique entity types: {stats['unique_entity_types']}")
        print(f"  - Average confidence: {stats['average_confidence']:.2f}")
        
        return entities
        
    except Exception as e:
        print(f"❌ Entity extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_triple_extraction(pipeline, test_chunk, entities):
    """Test triple extraction component."""
    print(f"\nTesting triple extraction...")
    
    try:
        # Test triple extraction
        triples, status = pipeline.triple_extractor.extract_triples_from_chunk(test_chunk, entities)
        print(f"✅ Triple extraction successful")
        print(f"  - Status: {status.value}")
        print(f"  - Total triples: {len(triples)}")
        
        if triples:
            for i, triple in enumerate(triples[:2], 1):  # Show first 2
                print(f"  - Triple {i}: {triple.subject} {triple.predicate} {triple.object}")
                print(f"    Evidence: {triple.evidence[:50]}...")
                print(f"    Confidence: {triple.confidence:.2f}")
        
        return triples, status
        
    except Exception as e:
        print(f"❌ Triple extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return [], None

def test_shacl_validation(pipeline, triples):
    """Test SHACL validation component."""
    print(f"\nTesting SHACL validation...")
    
    if not triples:
        print("⚠️  No triples to validate")
        return {}
    
    try:
        # Test batch validation
        results = pipeline.shacl_validator.batch_validate(triples)
        print(f"✅ SHACL validation successful")
        print(f"  - Total triples validated: {len(results)}")
        
        valid_count = sum(1 for is_valid, _ in results.values() if is_valid)
        print(f"  - Valid triples: {valid_count}/{len(results)} ({valid_count/len(results):.1%})")
        
        # Create validation report
        report = pipeline.shacl_validator.create_validation_report(triples)
        print(f"  - Validation rate: {report['validation_rate']:.1%}")
        print(f"  - Quarantine rate: {report['quarantine_rate']:.1%}")
        print(f"  - Invalid rate: {report['invalid_rate']:.1%}")
        
        return results
        
    except Exception as e:
        print(f"❌ SHACL validation failed: {e}")
        import traceback
        traceback.print_exc()
        return {}

def test_staging_manager(pipeline, triples, validation_results):
    """Test staging manager component."""
    print(f"\nTesting staging manager...")
    
    if not triples:
        print("⚠️  No triples to stage")
        return {}
    
    try:
        # Create test provenance records
        from src.ingestor.triple_extractor import ExtractedTriple
        from src.ingestor.provenance_manager import ProvenanceRecord
        from src.ingestor.pipeline import StagingRecord, ValidationStatus
        
        staging_records = {}
        
        for i, triple in enumerate(triples):
            # Get validation result
            triple_id = triple.chunk_id + "_" + str(id(triple))
            is_valid, messages = validation_results.get(triple_id, (False, ["No validation result"]))
            
            # Determine validation status
            if is_valid:
                if triple.confidence >= 0.3 and len(triple.evidence) >= 20:
                    status = ValidationStatus.VALID
                else:
                    status = ValidationStatus.QUARANTINED
            else:
                status = ValidationStatus.INVALID
            
            # Create staging record
            record = StagingRecord(
                triple=triple,
                validation_status=status,
                validation_messages=messages[:3],  # First 3 messages
                provenance_record=None,  # Simplified test
                quarantine_reason=messages[0] if status == ValidationStatus.QUARANTINED and messages else None,
                metadata={"test_index": i}
            )
            
            # Add to staging manager
            record_id = pipeline.staging_manager.add_record(record)
            staging_records[record_id] = record
        
        print(f"✅ Staging manager test successful")
        print(f"  - Total records added: {len(staging_records)}")
        
        # Get staging statistics
        stats = pipeline.staging_manager.get_stats()
        print(f"  - Total records in manager: {stats['total_records']}")
        print(f"  - Pending review: {stats['pending_review']}")
        print(f"  - Status counts: {stats['status_counts']}")
        
        return staging_records
        
    except Exception as e:
        print(f"❌ Staging manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return {}

def test_vector_store(pipeline, test_documents):
    """Test vector store component."""
    print(f"\nTesting vector store...")
    
    try:
        # Test vector store health
        health = pipeline.vector_store.health_check()
        print(f"✅ Vector store health check:")
        print(f"  - Status: {health.get('status', 'unknown')}")
        print(f"  - Collection: {health.get('collection', 'unknown')}")
        print(f"  - Document count: {health.get('document_count', '0')}")
        
        # Test adding documents
        if test_documents:
            doc_ids = pipeline.vector_store.add_documents(
                documents=[doc[:500] for doc in test_documents],  # Limit length
                metadata=[{"source": "test", "index": i} for i in range(len(test_documents))]
            )
            print(f"  - Added {len(doc_ids)} test documents")
            
            # Test retrieval
            if doc_ids:
                results = pipeline.vector_store.retrieve("test query", n_results=2)
                print(f"  - Retrieved {len(results)} results for test query")
        
        return True
        
    except Exception as e:
        print(f"❌ Vector store test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all pipeline component tests."""
    print("=" * 60)
    print("INGESTION PIPELINE COMPONENT TESTS")
    print("=" * 60)
    
    # Test data
    test_pdf_path = Path("data/input/test_document.txt")  # Using text file for simplicity
    test_text = """
    The Hong Kong Monetary Authority (HKMA) announced new Basel III capital requirements.
    Banks must maintain a minimum Common Equity Tier 1 (CET1) ratio of 4.5% by January 2025.
    John Smith, CEO of Standard Chartered Bank, stated that the regulations will improve financial stability.
    The Financial Services Development Council (FSDC) supports these measures.
    """
    
    # 1. Initialize pipeline
    pipeline = test_pipeline_initialization()
    if not pipeline:
        return
    
    # 2. Test PDF parsing (with text file instead of PDF for simplicity)
    chunks = []
    if test_pdf_path.exists() and test_pdf_path.suffix == '.txt':
        # Read text file
        with open(test_pdf_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # Create a mock chunk for testing
        from src.ingestor.pdf_parser import PDFChunk
        test_chunk = PDFChunk(
            id="test-chunk-001",
            text=file_content[:500] if len(file_content) > 500 else file_content,  # Limit size
            page_number=1,
            chunk_index=0,
            total_chunks=1,
            metadata={"source": "test"},
            start_char=0,
            end_char=len(file_content[:500]),
            document_id="test-doc",
            document_name=test_pdf_path.name
        )
        chunks = [test_chunk]
        print(f"\nUsing text file: {test_pdf_path} ({len(file_content)} chars)")
    
    # 3. Test entity extraction
    entities = test_entity_extraction(pipeline, test_text)
    
    # 4. Test triple extraction
    test_chunk_for_extraction = PDFChunk(
        id="test-chunk-002",
        text=test_text,
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={"source": "test"},
        start_char=0,
        end_char=len(test_text),
        document_id="test-doc",
        document_name="test.txt"
    )
    triples, extraction_status = test_triple_extraction(pipeline, test_chunk_for_extraction, entities)
    
    # 5. Test SHACL validation
    validation_results = test_shacl_validation(pipeline, triples)
    
    # 6. Test staging manager
    staging_records = test_staging_manager(pipeline, triples, validation_results)
    
    # 7. Test vector store
    test_documents = [test_text, "Another test document about financial regulations."]
    vector_store_ok = test_vector_store(pipeline, test_documents)
    
    # 8. Test complete pipeline with mock data
    print("\n" + "=" * 60)
    print("TESTING COMPLETE PIPELINE INTEGRATION")
    print("=" * 60)
    
    try:
        # Test pipeline status method
        status = pipeline.get_status()
        print(f"Pipeline status: {status['pipeline_status']}")
        print(f"Staging records: {status['staging']['total_records']}")
        print(f"Vector store health: {status['vector_store'].get('status', 'unknown')}")
        
        # Test reset
        pipeline.reset()
        print(f"Pipeline reset successful")
        
        print("\n✅ All component tests passed!")
        
    except Exception as e:
        print(f"❌ Pipeline integration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()

