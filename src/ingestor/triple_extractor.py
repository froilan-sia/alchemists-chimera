"""
Triple Extractor Module

This module provides functionality for extracting RDF triples (subject-predicate-object) 
from text chunks using Ollama LLM with sequential processing for Hugging Face Spaces 
free-tier compatibility.

Responsibilities:
- Triple extraction from text using Ollama qwen2.5:3b
- Evidence verification with case-insensitive substring checks
- Fallback predicate handling (chimera:relatedTo)
- Sequential processing (no parallelism) for resource constraints
- Retry logic with exponential backoff
- JSON prompt structure for reliable extraction
- Integration with PDFChunk and ExtractedEntity models

Note: This module uses sequential processing (not parallel) to be compatible with 
Hugging Face Spaces free-tier constraints.
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

import requests
from pydantic import BaseModel, Field, ValidationError
from requests.exceptions import RequestException, Timeout

from .pdf_parser import PDFChunk
from .entity_extractor import ExtractedEntity

logger = logging.getLogger(__name__)


class TripleExtractorConfig(BaseModel):
    """Configuration for triple extraction."""
    
    ollama_base_url: str = Field(
        default="http://localhost:11434", 
        description="Base URL for Ollama API"
    )
    model_name: str = Field(
        default="qwen2.5:3b", 
        description="Ollama model to use for extraction"
    )
    max_tokens: int = Field(
        default=2048, 
        ge=100, 
        le=4096, 
        description="Maximum tokens for LLM response"
    )
    temperature: float = Field(
        default=0.1, 
        ge=0.0, 
        le=2.0, 
        description="Temperature for LLM generation"
    )
    max_retries: int = Field(
        default=3, 
        ge=0, 
        le=10, 
        description="Maximum retry attempts for API calls"
    )
    retry_delay_base: float = Field(
        default=1.0, 
        ge=0.1, 
        le=10.0, 
        description="Base delay for exponential backoff (seconds)"
    )
    timeout_seconds: float = Field(
        default=30.0, 
        ge=5.0, 
        le=120.0, 
        description="Timeout for API calls (seconds)"
    )
    max_triples_per_chunk: int = Field(
        default=10, 
        ge=1, 
        le=50, 
        description="Maximum triples to extract per chunk"
    )
    min_evidence_length: int = Field(
        default=20, 
        ge=10, 
        le=100, 
        description="Minimum length of evidence quote"
    )
    confidence_threshold: float = Field(
        default=0.5, 
        ge=0.0, 
        le=1.0, 
        description="Minimum confidence for extracted triples"
    )
    fallback_predicate: str = Field(
        default="chimera:relatedTo", 
        description="Fallback predicate when extraction fails"
    )
    entity_prefix: str = Field(
        default="chimera:", 
        description="Prefix for extracted entities in triples"
    )
    predicate_prefix: str = Field(
        default="chimera:", 
        description="Prefix for extracted predicates in triples"
    )


class ExtractionStatus(str, Enum):
    """Status of triple extraction."""
    
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExtractedTriple:
    """Represents an extracted RDF triple with evidence and metadata."""
    
    subject: str
    predicate: str
    object: str
    evidence: str  # Original text that supports the triple
    confidence: float  # 0-1 confidence score
    chunk_id: str  # Source chunk identifier
    entity_anchors: List[str]  # List of entity IDs that anchor this triple
    metadata: Dict[str, Any]
    extraction_timestamp: datetime = datetime.now()
    
    def to_turtle(self) -> str:
        """Convert triple to Turtle RDF format.
        
        Returns:
            Turtle representation of the triple
        """
        # Escape quotes in values
        subj = self.subject.replace('"', '\\"')
        pred = self.predicate.replace('"', '\\"')
        obj = self.object.replace('"', '\\"')
        
        return f'{subj} {pred} "{obj}" .'
    
    def to_json(self) -> Dict[str, Any]:
        """Convert triple to JSON serializable dictionary.
        
        Returns:
            JSON representation of the triple
        """
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "chunk_id": self.chunk_id,
            "entity_anchors": self.entity_anchors,
            "metadata": self.metadata,
            "extraction_timestamp": self.extraction_timestamp.isoformat(),
        }


class TripleExtractorError(Exception):
    """Custom exception for triple extraction errors."""
    pass


class TripleExtractor:
    """Main triple extraction class using Ollama LLM with sequential processing."""
    
    def __init__(self, config: Optional[TripleExtractorConfig] = None):
        """Initialize triple extractor with configuration.
        
        Args:
            config: Optional configuration object. Uses defaults if not provided.
        """
        self.config = config or TripleExtractorConfig()
        self.session = requests.Session()
        
        # Configure session for better reliability
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AlchemistsChimera/1.0'
        })
        
        logger.info(f"Initialized TripleExtractor with config: {self.config}")
        logger.info(f"Using model: {self.config.model_name} at {self.config.ollama_base_url}")
    
    def extract_triples_from_chunk(
        self, 
        chunk: PDFChunk, 
        entities: Optional[List[ExtractedEntity]] = None
    ) -> Tuple[List[ExtractedTriple], ExtractionStatus]:
        """Extract triples from a single PDF chunk.
        
        Uses sequential processing (not parallel) for Hugging Face compatibility.
        
        Args:
            chunk: PDF chunk to extract triples from
            entities: Optional list of entities to use as anchors
            
        Returns:
            Tuple of (list of extracted triples, extraction status)
            
        Raises:
            TripleExtractorError: If extraction fails after all retries
        """
        if not chunk.text or not chunk.text.strip():
            logger.warning(f"Empty chunk {chunk.id}, skipping extraction")
            return [], ExtractionStatus.SKIPPED
        
        logger.info(f"Extracting triples from chunk: {chunk.id}")
        logger.debug(f"Chunk text length: {len(chunk.text)} chars")
        
        # Prepare entity anchors
        entity_anchors = self._prepare_entity_anchors(entities) if entities else []
        
        try:
            # Generate prompt for this chunk
            prompt = self._generate_extraction_prompt(chunk.text, entity_anchors)
            
            # Call Ollama API with retry logic
            response_data = self._call_ollama_with_retry(prompt)
            
            # Parse response and validate triples
            triples = self._parse_and_validate_response(
                response_data, 
                chunk.id, 
                chunk.text, 
                entity_anchors
            )
            
            # Apply confidence filtering
            triples = [t for t in triples if t.confidence >= self.config.confidence_threshold]
            
            # Limit number of triples
            if len(triples) > self.config.max_triples_per_chunk:
                triples.sort(key=lambda t: t.confidence, reverse=True)
                triples = triples[:self.config.max_triples_per_chunk]
                logger.info(f"Limited triples to top {self.config.max_triples_per_chunk} by confidence")
            
            status = ExtractionStatus.SUCCESS if triples else ExtractionStatus.PARTIAL
            
            logger.info(f"Extracted {len(triples)} triples from chunk {chunk.id} (status: {status})")
            return triples, status
            
        except Exception as e:
            logger.error(f"Failed to extract triples from chunk {chunk.id}: {e}")
            
            # Create fallback triple if extraction fails completely
            fallback_triples = self._create_fallback_triples(chunk, entities)
            return fallback_triples, ExtractionStatus.FAILED
    
    def extract_triples_from_chunks(
        self, 
        chunks: List[PDFChunk], 
        entities_by_chunk: Optional[Dict[str, List[ExtractedEntity]]] = None
    ) -> Dict[str, Tuple[List[ExtractedTriple], ExtractionStatus]]:
        """Extract triples from multiple PDF chunks sequentially.
        
        Uses sequential processing (not parallel) to be compatible with 
        Hugging Face Spaces free-tier constraints.
        
        Args:
            chunks: List of PDF chunks to extract triples from
            entities_by_chunk: Optional dictionary mapping chunk_id to entities
            
        Returns:
            Dictionary mapping chunk_id to (triples, status)
            
        Raises:
            TripleExtractorError: If extraction fails for critical chunks
        """
        results = {}
        total_chunks = len(chunks)
        
        logger.info(f"Starting sequential triple extraction from {total_chunks} chunks")
        
        for i, chunk in enumerate(chunks, 1):
            # Progress logging
            logger.info(f"Processing chunk {i}/{total_chunks}: {chunk.id}")
            
            # Get entities for this chunk if available
            entities = None
            if entities_by_chunk and chunk.id in entities_by_chunk:
                entities = entities_by_chunk[chunk.id]
                logger.debug(f"Using {len(entities)} entities as anchors for chunk {chunk.id}")
            
            try:
                # Sequential processing - no parallelism
                triples, status = self.extract_triples_from_chunk(chunk, entities)
                results[chunk.id] = (triples, status)
                
                # Add small delay between chunks to avoid overwhelming resources
                if i < total_chunks:
                    time.sleep(0.5)  # 500ms delay between chunks
                    
            except Exception as e:
                logger.error(f"Critical error extracting triples from chunk {chunk.id}: {e}")
                results[chunk.id] = ([], ExtractionStatus.FAILED)
                # Continue with next chunk instead of failing completely
        
        logger.info(f"Completed triple extraction from {total_chunks} chunks")
        return results
    
    def _generate_extraction_prompt(self, text: str, entity_anchors: List[str]) -> str:
        """Generate structured prompt for triple extraction.
        
        Args:
            text: Source text to extract triples from
            entity_anchors: List of entity names to focus on
            
        Returns:
            Structured prompt for LLM
        """
        # Build entity context if available
        entity_context = ""
        if entity_anchors:
            entity_list = ", ".join(entity_anchors)
            entity_context = f"\nRelevant entities to focus on: {entity_list}"
        
        prompt = f"""Extract structured relationships (triples) from the following text.
For each triple, identify:
1. Subject (entity or concept)
2. Predicate (relationship verb or phrase)
3. Object (entity, concept, or value)
4. Evidence (exact quote from text supporting the triple)

Format requirements:
- Return ONLY valid JSON array of objects
- Each object must have: subject, predicate, object, evidence, confidence (0-1)
- Use prefix "{self.config.entity_prefix}" for subjects and objects that are entities
- Use prefix "{self.config.predicate_prefix}" for predicates
- Confidence should reflect certainty about extraction (0.0-1.0)
- Evidence must be an exact substring from the original text
- Maximum {self.config.max_triples_per_chunk} triples

Example response format:
[
  {{
    "subject": "{self.config.entity_prefix}Basel_Committee",
    "predicate": "{self.config.predicate_prefix}develops",
    "object": "{self.config.entity_prefix}Basel_III_framework",
    "evidence": "The Basel III framework was developed by the Basel Committee",
    "confidence": 0.95
  }}
]

Text to analyze:{entity_context}
"{text}"

Extracted triples (JSON array):
"""
        
        return prompt
    
    def _call_ollama_with_retry(self, prompt: str) -> Dict[str, Any]:
        """Call Ollama API with exponential backoff retry logic.
        
        Args:
            prompt: Prompt to send to Ollama
            
        Returns:
            Response data from Ollama
            
        Raises:
            TripleExtractorError: If all retries fail
        """
        url = f"{self.config.ollama_base_url}/api/generate"
        
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(f"Calling Ollama API (attempt {attempt + 1}/{self.config.max_retries + 1})")
                
                response = self.session.post(
                    url, 
                    json=payload, 
                    timeout=self.config.timeout_seconds
                )
                response.raise_for_status()
                
                data = response.json()
                
                if "response" not in data:
                    raise ValueError("Invalid response format from Ollama")
                
                logger.debug(f"Successfully received response from Ollama")
                return data
                
            except (RequestException, Timeout, ValueError) as e:
                logger.warning(f"Ollama API call failed (attempt {attempt + 1}): {e}")
                
                if attempt < self.config.max_retries:
                    # Exponential backoff
                    delay = self.config.retry_delay_base * (2 ** attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"All {self.config.max_retries + 1} attempts failed")
                    raise TripleExtractorError(f"Failed to call Ollama API after {self.config.max_retries + 1} attempts: {e}")
    
    def _parse_and_validate_response(
        self, 
        response_data: Dict[str, Any], 
        chunk_id: str, 
        original_text: str, 
        entity_anchors: List[str]
    ) -> List[ExtractedTriple]:
        """Parse LLM response and validate extracted triples.
        
        Args:
            response_data: Response from Ollama API
            chunk_id: Source chunk identifier
            original_text: Original text for evidence verification
            entity_anchors: List of entity names for anchoring
            
        Returns:
            List of validated extracted triples
        """
        try:
            # Extract response text
            response_text = response_data.get("response", "").strip()
            
            # Clean up response (remove markdown, code blocks, etc.)
            response_text = self._clean_response_text(response_text)
            
            # Parse JSON from response
            try:
                triples_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from response: {e}")
                logger.debug(f"Raw response: {response_text[:500]}...")
                return []
            
            # Validate response format
            if not isinstance(triples_data, list):
                logger.warning(f"Expected list but got {type(triples_data)}")
                return []
            
            validated_triples = []
            
            for i, triple_data in enumerate(triples_data):
                try:
                    # Validate required fields
                    required_fields = ["subject", "predicate", "object", "evidence", "confidence"]
                    if not all(field in triple_data for field in required_fields):
                        logger.warning(f"Missing required fields in triple {i}")
                        continue
                    
                    subject = str(triple_data["subject"]).strip()
                    predicate = str(triple_data["predicate"]).strip()
                    obj = str(triple_data["object"]).strip()
                    evidence = str(triple_data["evidence"]).strip()
                    confidence = float(triple_data["confidence"])
                    
                    # Validate confidence range
                    if not 0.0 <= confidence <= 1.0:
                        logger.warning(f"Invalid confidence {confidence} in triple {i}, clamping to [0,1]")
                        confidence = max(0.0, min(1.0, confidence))
                    
                    # Validate evidence
                    if not self._validate_evidence(evidence, original_text):
                        logger.warning(f"Evidence not found in original text for triple {i}")
                        continue
                    
                    # Ensure proper prefixes
                    if not subject.startswith(self.config.entity_prefix):
                        subject = f"{self.config.entity_prefix}{subject}"
                    if not predicate.startswith(self.config.predicate_prefix):
                        predicate = f"{self.config.predicate_prefix}{predicate}"
                    if not obj.startswith(self.config.entity_prefix):
                        obj = f"{self.config.entity_prefix}{obj}"
                    
                    # Normalize entity anchors
                    normalized_anchors = self._find_entity_anchors(subject, obj, entity_anchors)
                    
                    # Create extracted triple
                    triple = ExtractedTriple(
                        subject=subject,
                        predicate=predicate,
                        object=obj,
                        evidence=evidence,
                        confidence=confidence,
                        chunk_id=chunk_id,
                        entity_anchors=normalized_anchors,
                        metadata={
                            "response_index": i,
                            "total_response_triples": len(triples_data),
                            "model_name": self.config.model_name,
                            "validation_status": "validated",
                        }
                    )
                    
                    validated_triples.append(triple)
                    logger.debug(f"Validated triple {i}: {subject} {predicate} {obj}")
                    
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Error parsing triple {i}: {e}")
                    continue
            
            logger.info(f"Parsed and validated {len(validated_triples)}/{len(triples_data)} triples")
            return validated_triples
            
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return []
    
    def _clean_response_text(self, text: str) -> str:
        """Clean up LLM response text to extract JSON.
        
        Args:
            text: Raw response text from LLM
            
        Returns:
            Cleaned text with JSON content
        """
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Find JSON array start and end
        json_start = text.find('[')
        json_end = text.rfind(']')
        
        if json_start >= 0 and json_end > json_start:
            text = text[json_start:json_end + 1]
        
        return text
    
    def _validate_evidence(self, evidence: str, original_text: str) -> bool:
        """Validate that evidence quote exists in original text (case-insensitive).
        
        Args:
            evidence: Evidence quote to validate
            original_text: Original text to search in
            
        Returns:
            True if evidence is valid substring, False otherwise
        """
        if not evidence or len(evidence) < self.config.min_evidence_length:
            return False
        
        # Case-insensitive substring check
        evidence_lower = evidence.lower()
        original_lower = original_text.lower()
        
        return evidence_lower in original_lower
    
    def _find_entity_anchors(
        self, 
        subject: str, 
        obj: str, 
        entity_anchors: List[str]
    ) -> List[str]:
        """Find entity anchors for subject and object.
        
        Args:
            subject: Subject of triple
            obj: Object of triple
            entity_anchors: List of entity names
            
        Returns:
            List of entity anchors that match subject or object
        """
        anchors = []
        
        # Remove prefixes for matching
        subject_clean = subject.replace(self.config.entity_prefix, "")
        obj_clean = obj.replace(self.config.entity_prefix, "")
        
        # Case-insensitive matching
        for entity in entity_anchors:
            entity_lower = entity.lower()
            
            if entity_lower in subject_clean.lower() or subject_clean.lower() in entity_lower:
                anchors.append(entity)
            elif entity_lower in obj_clean.lower() or obj_clean.lower() in entity_lower:
                anchors.append(entity)
        
        return anchors
    
    def _prepare_entity_anchors(self, entities: List[ExtractedEntity]) -> List[str]:
        """Prepare entity names for use as anchors.
        
        Args:
            entities: List of extracted entities
            
        Returns:
            List of entity names normalized for matching
        """
        anchors = []
        seen = set()
        
        for entity in entities:
            # Use normalized text for consistency
            anchor = entity.normalized_text
            
            # Add entity type suffix for better matching
            anchor_with_type = f"{anchor}_{entity.entity_type.lower()}"
            
            if anchor_with_type not in seen:
                anchors.append(anchor_with_type)
                seen.add(anchor_with_type)
        
        return anchors
    
    def _create_fallback_triples(
        self, 
        chunk: PDFChunk, 
        entities: Optional[List[ExtractedEntity]]
    ) -> List[ExtractedTriple]:
        """Create fallback triples when extraction fails.
        
        Args:
            chunk: PDF chunk
            entities: Optional list of entities
            
        Returns:
            List of fallback triples
        """
        fallback_triples = []
        
        if entities and len(entities) >= 2:
            # Create fallback relationships between entities
            for i in range(min(len(entities), 3)):
                for j in range(i + 1, min(len(entities), i + 3)):
                    subject = f"{self.config.entity_prefix}{entities[i].normalized_text}"
                    object = f"{self.config.entity_prefix}{entities[j].normalized_text}"
                    
                    # Create a generic evidence quote
                    evidence = f"{entities[i].text} mentioned with {entities[j].text}"
                    
                    triple = ExtractedTriple(
                        subject=subject,
                        predicate=self.config.fallback_predicate,
                        object=object,
                        evidence=evidence,
                        confidence=0.3,  # Low confidence for fallback
                        chunk_id=chunk.id,
                        entity_anchors=[entities[i].normalized_text, entities[j].normalized_text],
                        metadata={
                            "fallback_type": "entity_relation",
                            "entity_types": [entities[i].entity_type, entities[j].entity_type],
                            "extraction_status": "fallback",
                        }
                    )
                    
                    fallback_triples.append(triple)
            
            logger.info(f"Created {len(fallback_triples)} fallback triples for chunk {chunk.id}")
        
        return fallback_triples
    
    def batch_extract_with_entities(
        self, 
        chunks: List[PDFChunk], 
        entity_extractor: Any
    ) -> Dict[str, Tuple[List[ExtractedTriple], ExtractionStatus]]:
        """Batch extract triples with integrated entity extraction.
        
        Args:
            chunks: List of PDF chunks
            entity_extractor: EntityExtractor instance
            
        Returns:
            Dictionary mapping chunk_id to (triples, status)
        """
        logger.info("Starting batch extraction with integrated entity extraction")
        
        # Extract entities from chunks sequentially
        entities_by_chunk = {}
        
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"Extracting entities from chunk {i}/{len(chunks)}: {chunk.id}")
            
            try:
                entities = entity_extractor.extract_entities(chunk.text, chunk.id)
                entities_by_chunk[chunk.id] = entities
                logger.debug(f"Extracted {len(entities)} entities from chunk {chunk.id}")
                
            except Exception as e:
                logger.error(f"Failed to extract entities from chunk {chunk.id}: {e}")
                entities_by_chunk[chunk.id] = []
        
        # Extract triples using the extracted entities
        return self.extract_triples_from_chunks(chunks, entities_by_chunk)
    
    def test_ollama_connection(self) -> bool:
        """Test connection to Ollama API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.config.ollama_base_url}/api/tags"
            response = self.session.get(url, timeout=10.0)
            response.raise_for_status()
            
            data = response.json()
            models = data.get("models", [])
            
            logger.info(f"Ollama connection successful. Available models: {len(models)}")
            
            # Check if our model is available
            model_names = [model.get("name") for model in models]
            if self.config.model_name in model_names:
                logger.info(f"Model {self.config.model_name} is available")
                return True
            else:
                logger.warning(f"Model {self.config.model_name} not found. Available: {model_names}")
                return False
                
        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False
    
    @classmethod
    def create_default_extractor(cls) -> 'TripleExtractor':
        """Create an extractor with default configuration.
        
        Returns:
            TripleExtractor instance with default config
        """
        return cls(TripleExtractorConfig())


def main():
    """Example usage and testing of triple extractor."""
    import sys
    from pathlib import Path
    
    print("Testing Triple Extractor...")
    print("=" * 60)
    
    # Sample text for testing
    sample_text = """
    The Hong Kong Monetary Authority (HKMA) announced new Basel III capital requirements.
    Banks must maintain a minimum Common Equity Tier 1 (CET1) ratio of 4.5% by January 2025.
    John Smith, CEO of Standard Chartered Bank, stated that the regulations will improve financial stability.
    The Financial Services Development Council (FSDC) supports these measures.
    """
    
    # Create mock chunk and entities
    chunk = PDFChunk(
        id="test-chunk-001",
        text=sample_text,
        page_number=1,
        chunk_index=0,
        total_chunks=1,
        metadata={"test": True},
        start_char=0,
        end_char=len(sample_text),
        document_id="test-doc",
        document_name="test.pdf"
    )
    
    # Mock entities
    entities = [
        ExtractedEntity(
            text="Hong Kong Monetary Authority",
            entity_type="ORG",
            start_char=4,
            end_char=34,
            confidence=0.9,
            context="The Hong Kong Monetary Authority announced new requirements",
            normalized_text="hong kong monetary authority",
            metadata={}
        ),
        ExtractedEntity(
            text="Basel III",
            entity_type="LAW",
            start_char=48,
            end_char=57,
            confidence=0.8,
            context="Basel III capital requirements",
            normalized_text="basel iii",
            metadata={}
        ),
    ]
    
    try:
        # Create extractor
        extractor = TripleExtractor.create_default_extractor()
        
        # Test connection
        print("\nTesting Ollama connection...")
        if extractor.test_ollama_connection():
            print("✅ Ollama connection successful")
        else:
            print("⚠️  Ollama connection may have issues, but continuing anyway...")
        
        # Extract triples
        print("\nExtracting triples from sample text...")
        triples, status = extractor.extract_triples_from_chunk(chunk, entities)
        
        # Display results
        print(f"\nExtraction status: {status}")
        print(f"Extracted {len(triples)} triples:")
        
        for i, triple in enumerate(triples, 1):
            print(f"\n{i}. {triple.subject} {triple.predicate} {triple.object}")
            print(f"   Confidence: {triple.confidence:.2f}")
            print(f"   Evidence: {triple.evidence[:80]}...")
            print(f"   Anchors: {triple.entity_anchors}")
        
        # Test with multiple chunks
        print("\n" + "=" * 60)
        print("Testing sequential batch extraction...")
        
        chunks = [chunk, chunk]  # Duplicate for testing
        
        # Mock entities by chunk
        entities_by_chunk = {
            "test-chunk-001": entities,
            "test-chunk-002": entities[:1],  # Only first entity
        }
        
        batch_results = extractor.extract_triples_from_chunks(chunks, entities_by_chunk)
        
        for chunk_id, (chunk_triples, chunk_status) in batch_results.items():
            print(f"Chunk {chunk_id}: {len(chunk_triples)} triples, status: {chunk_status}")
        
        print("\n✅ Triple extractor test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
