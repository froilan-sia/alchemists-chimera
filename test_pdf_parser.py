#!/usr/bin/env python3
"""Test script for PDF parser functionality."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ingestor.pdf_parser import PDFParser, PDFParserConfig

def test_basic_functionality():
    """Test basic PDF parser functionality."""
    print("Testing PDF Parser...")
    
    # Create a test directory if it doesn't exist
    test_dir = Path("data/input")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a simple text file to test
    test_file = test_dir / "test_document.txt"
    test_file.write_text("This is a test document for the PDF parser. " * 50)
    
    # Convert to PDF (we'll simulate with text file for now)
    # In real scenario, this would be an actual PDF
    print(f"Created test file: {test_file}")
    
    # Test with custom config
    config = PDFParserConfig(
        chunk_size=500,
        chunk_overlap=50,
        max_pages=10
    )
    
    parser = PDFParser(config)
    
    # Since we don't have actual PDF, let's test the class methods
    print("\nTesting parser methods:")
    
    # Test document ID generation
    doc_id = parser._generate_document_id(Path("test.pdf"), None)
    print(f"Generated document ID: {doc_id}")
    
    # Test chunk ID generation
    chunk_id = parser._generate_chunk_id("test-doc", 0, 0)
    print(f"Generated chunk ID: {chunk_id}")
    
    # Test config validation
    print(f"Parser config: {config}")
    
    print("\nPDF Parser test completed successfully!")
    
    # Clean up
    test_file.unlink(missing_ok=True)

if __name__ == "__main__":
    try:
        test_basic_functionality()
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

