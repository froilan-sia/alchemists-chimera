#!/usr/bin/env python3
"""Test script for PDF parser functionality."""

import sys
from pathlib import Path
from unittest.mock import Mock
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ingestor.pdf_parser import PDFParser, PDFParserConfig

def test_pdf_parser_functionality():
    """Test PDF parser functionality with mocked PDF."""
    print("Testing PDF Parser Functionality...")
    
    # Test configuration
    config = PDFParserConfig(
        chunk_size=300,
        chunk_overlap=50,
        max_pages=5
    )
    
    parser = PDFParser(config)
    
    print(f"1. Created parser with config:")
    print(f"   - Chunk size: {config.chunk_size}")
    print(f"   - Chunk overlap: {config.chunk_overlap}")
    print(f"   - Max pages: {config.max_pages}")
    
    # Test document ID generation with mock reader
    mock_reader = Mock()
    mock_reader.metadata = {
        '/Title': 'Test Document',
        '/Author': 'Test Author',
        '/Creator': 'PDF Test Generator'
    }
    
    test_pdf_path = Path("/tmp/test.pdf")
    doc_id = parser._generate_document_id(test_pdf_path, mock_reader)
    print(f"\n2. Generated document ID: {doc_id}")
    
    # Test chunk ID generation
    chunk_id = parser._generate_chunk_id("test-doc-abc123", 5, 12)
    print(f"3. Generated chunk ID: {chunk_id}")
    
    # Test chunk ID with single digit
    chunk_id_simple = parser._generate_chunk_id("simple", 0, 0)
    print(f"4. Simple chunk ID: {chunk_id_simple}")
    
    # Test PDFChunk dataclass
    print("\n5. Testing PDFChunk dataclass structure:")
    
    # Create a sample chunk
    from ingestor.pdf_parser import PDFChunk
    
    sample_chunk = PDFChunk(
        id="test-001-page1-chunk0",
        text="This is a sample text chunk extracted from a PDF document.",
        page_number=1,
        chunk_index=0,
        total_chunks=3,
        metadata={"source": "test", "confidence": 0.95},
        start_char=0,
        end_char=50,
        document_id="test-001",
        document_name="test_document.pdf"
    )
    
    print(f"   - Chunk ID: {sample_chunk.id}")
    print(f"   - Page: {sample_chunk.page_number}")
    print(f"   - Text length: {len(sample_chunk.text)} chars")
    print(f"   - Document: {sample_chunk.document_name}")
    
    # Test parser class methods
    print("\n6. Testing parser class methods:")
    
    # Create default parser
    default_parser = PDFParser.create_default_parser()
    print(f"   - Default parser chunk size: {default_parser.config.chunk_size}")
    print(f"   - Default parser chunk overlap: {default_parser.config.chunk_overlap}")
    
    print("\n✅ All PDF parser tests completed successfully!")
    
    return True

def test_error_handling():
    """Test error handling in PDF parser."""
    print("\nTesting Error Handling...")
    
    parser = PDFParser()
    
    # Test file not found
    try:
        parser.parse_pdf(Path("/non/existent/file.pdf"))
        print("❌ Should have raised FileNotFoundError")
        return False
    except FileNotFoundError as e:
        print(f"✅ Correctly raised FileNotFoundError: {str(e)[:50]}...")
    except Exception as e:
        print(f"❌ Wrong exception type: {type(e).__name__}: {e}")
        return False
    
    print("✅ Error handling tests completed successfully!")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("PDF Parser Unit Tests")
    print("=" * 60)
    
    try:
        # Test basic functionality
        if not test_pdf_parser_functionality():
            sys.exit(1)
        
        # Test error handling
        if not test_error_handling():
            sys.exit(1)
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

