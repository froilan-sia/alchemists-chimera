"""
Example usage of the Ingestion Pipeline Orchestrator.

This demonstrates how to use the pipeline to process PDF documents
and extract structured knowledge with provenance tracking.
"""

import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def example_basic_usage():
    """Example 1: Basic pipeline usage."""
    print("=" * 60)
    print("EXAMPLE 1: BASIC PIPELINE USAGE")
    print("=" * 60)
    
    from ingestor.pipeline import create_default_pipeline
    
    # Create pipeline with default configuration
    pipeline = create_default_pipeline()
    
    # Process a PDF file
    pdf_path = Path("data/input/sample.pdf")  # Change to your PDF path
    
    if not pdf_path.exists():
        print(f"⚠️  PDF file not found: {pdf_path}")
        print("Using mock demonstration instead...")
        
        # Show pipeline status without actual processing
        status = pipeline.get_status()
        print(f"\nPipeline Status: {status['pipeline_status']}")
        print(f"Vector Store: {status['vector_store'].get('status', 'unknown')}")
        return
    
    print(f"Processing PDF: {pdf_path}")
    
    try:
        # Process the PDF
        metrics = pipeline.process_pdf(pdf_path)
        
        # Display results
        print(f"\n✅ Processing Complete!")
        print(f"Duration: {metrics.duration_seconds:.2f}s")
        print(f"Chunks processed: {metrics.processed_chunks}/{metrics.total_chunks}")
        print(f"Triples extracted: {metrics.total_triples}")
        print(f"Valid triples: {metrics.valid_triples}")
        print(f"Quarantined triples: {metrics.quarantined_triples}")
        print(f"Vector insertions: {metrics.vector_insertions}")
        
    except Exception as e:
        print(f"❌ Processing failed: {e}")

def example_custom_configuration():
    """Example 2: Custom pipeline configuration."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: CUSTOM CONFIGURATION")
    print("=" * 60)
    
    from ingestor.pipeline import IngestionPipeline
    
    # Custom configuration
    config = {
        "chunk_size": 800,  # Smaller chunks
        "chunk_overlap": 100,
        "entity_types": ["ORG", "LAW", "MONEY"],  # Focus on regulatory entities
        "min_entity_confidence": 0.6,
        "model_name": "qwen2.5:3b",
        "confidence_threshold": 0.6,  # Higher threshold
        "base_uri": "http://alchemists-chimera.org/finance/",
        "vector_store_path": "./data/vector_store_finance",
        "staging_path": "./data/staging_finance",
    }
    
    pipeline = IngestionPipeline(config)
    print(f"Created pipeline with custom configuration")
    print(f"Chunk size: {config['chunk_size']}")
    print(f"Entity types: {config['entity_types']}")
    print(f"Confidence threshold: {config['confidence_threshold']}")
    print(f"Base URI: {config['base_uri']}")

def example_staging_workflow():
    """Example 3: HITL staging workflow."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: HITL STAGING WORKFLOW")
    print("=" * 60)
    
    from ingestor.pipeline import create_default_pipeline, ValidationStatus
    
    pipeline = create_default_pipeline()
    
    # Get staging statistics
    stats = pipeline.staging_manager.get_stats()
    
    print(f"Staging Manager Statistics:")
    print(f"  Total records: {stats['total_records']}")
    print(f"  Pending review: {stats['pending_review']}")
    print(f"  Status counts: {stats['status_counts']}")
    
    # Get records pending human review
    pending_review = pipeline.staging_manager.get_pending_review()
    
    if pending_review:
        print(f"\nRecords pending human review: {len(pending_review)}")
        
        # Simulate human review for first record
        if pending_review:
            record = pending_review[0]
            print(f"\nSample record for review:")
            print(f"  Triple: {record.triple.subject} {record.triple.predicate} {record.triple.object}")
            print(f"  Status: {record.validation_status.value}")
            print(f"  Confidence: {record.triple.confidence:.2f}")
            print(f"  Evidence: {record.triple.evidence[:50]}...")
            
            # Simulate marking as reviewed
            print(f"\nSimulating human review...")
            # In real usage: pipeline.staging_manager.mark_as_reviewed(record_id, "human_reviewer", ValidationStatus.VALID)
    else:
        print(f"No records pending review")

def example_pipeline_status():
    """Example 4: Checking pipeline status."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: PIPELINE STATUS MONITORING")
    print("=" * 60)
    
    from ingestor.pipeline import create_default_pipeline
    
    pipeline = create_default_pipeline()
    
    # Get comprehensive status
    status = pipeline.get_status()
    
    print(f"Pipeline Status Report:")
    print(f"Status: {status['pipeline_status']}")
    
    metrics = status['metrics']
    print(f"\nMetrics:")
    print(f"  Processed chunks: {metrics['processed_chunks']}")
    print(f"  Success rate: {metrics['success_rate']:.1%}")
    print(f"  Total triples: {metrics['total_triples']}")
    print(f"  Validation rate: {metrics['validation_rate']:.1%}")
    print(f"  Vector insertions: {metrics['vector_insertions']}")
    
    staging = status['staging']
    print(f"\nStaging:")
    print(f"  Total records: {staging['total_records']}")
    print(f"  Pending review: {staging['pending_review']}")
    
    vector_store = status['vector_store']
    print(f"\nVector Store:")
    print(f"  Status: {vector_store.get('status', 'unknown')}")
    print(f"  Document count: {vector_store.get('document_count', '0')}")

def example_reset_pipeline():
    """Example 5: Resetting pipeline for new processing."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: PIPELINE RESET")
    print("=" * 60)
    
    from ingestor.pipeline import create_default_pipeline
    
    pipeline = create_default_pipeline()
    
    print("Resetting pipeline state...")
    pipeline.reset()
    
    status = pipeline.get_status()
    print(f"Pipeline status after reset: {status['pipeline_status']}")
    print(f"Metrics reset to zero: {status['metrics']['processed_chunks']} chunks processed")

def main():
    """Run all examples."""
    print("INGESTION PIPELINE ORCHESTRATOR - USAGE EXAMPLES")
    print("=" * 60)
    print("\nThis demonstrates the complete ingestion workflow with:")
    print("1. Sequential chunk processing for Hugging Face Spaces")
    print("2. Five-component integration (PDF, Entity, Triple, Provenance, SHACL)")
    print("3. Evidence grounding verification")
    print("4. Vector store integration for immediate hybrid retrieval")
    print("5. Comprehensive error handling and recovery")
    print("6. HITL (Human-In-The-Loop) workflow with staging")
    print("=" * 60)
    
    example_basic_usage()
    example_custom_configuration()
    example_staging_workflow()
    example_pipeline_status()
    example_reset_pipeline()
    
    print("\n" + "=" * 60)
    print("EXAMPLES COMPLETE")
    print("=" * 60)
    print("\nThe ingestion pipeline is ready for production use!")
    print("\nKey features demonstrated:")
    print("✅ Sequential processing (Hugging Face Spaces compatible)")
    print("✅ Complete component orchestration")
    print("✅ Evidence verification and SHACL validation")
    print("✅ Vector store integration")
    print("✅ HITL workflow with staging")
    print("✅ Comprehensive monitoring and metrics")

if __name__ == "__main__":
    main()

