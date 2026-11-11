"""
Entity Anchor Extractor Module

This module provides functionality for extracting named entities from text
using spaCy NLP models. The extracted entities serve as verified anchors
for the triple extraction process.

Responsibilities:
- Named entity recognition using spaCy en_core_web_sm model
- Entity filtering to relevant types (ORG, PERSON, LAW, MONEY, GPE)
- Confidence scoring and entity deduplication
- Integration with PDF chunks for entity anchoring
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

import spacy
from spacy.tokens import Doc, Span
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Entity types relevant for regulatory document processing."""
    
    ORGANIZATION = "ORG"
    PERSON = "PERSON"
    LAW = "LAW"
    MONEY = "MONEY"
    GEO_POLITICAL = "GPE"
    DATE = "DATE"
    PERCENT = "PERCENT"
    QUANTITY = "QUANTITY"
    PRODUCT = "PRODUCT"
    EVENT = "EVENT"
    WORK_OF_ART = "WORK_OF_ART"
    NORP = "NORP"  # Nationalities or religious or political groups
    FACILITY = "FAC"  # Buildings, airports, highways, bridges, etc.
    LANGUAGE = "LANGUAGE"
    
    @classmethod
    def regulatory_entities(cls) -> List[str]:
        """Get entity types relevant for regulatory document processing."""
        return [
            cls.ORGANIZATION.value,
            cls.PERSON.value,
            cls.LAW.value,
            cls.MONEY.value,
            cls.GEO_POLITICAL.value,
            cls.DATE.value,
            cls.PERCENT.value,
            cls.QUANTITY.value,
        ]


class EntityExtractorConfig(BaseModel):
    """Configuration for entity extraction."""
    
    model_name: str = Field(default="en_core_web_sm", description="spaCy model to use")
    entity_types: List[str] = Field(
        default_factory=lambda: EntityType.regulatory_entities(),
        description="Entity types to extract"
    )
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum confidence score for entities")
    deduplicate_entities: bool = Field(default=True, description="Remove duplicate entities")
    max_entities_per_chunk: Optional[int] = Field(default=None, ge=1, description="Maximum entities to extract per chunk")
    include_context_words: int = Field(default=3, ge=0, le=10, description="Number of context words to include around entity")
    normalize_entities: bool = Field(default=True, description="Normalize entity text (lowercase, strip)")


@dataclass
class ExtractedEntity:
    """Represents an extracted named entity."""
    
    text: str
    entity_type: str
    start_char: int
    end_char: int
    confidence: float
    context: str
    normalized_text: str
    metadata: Dict[str, Any]
    
    def __hash__(self):
        """Hash based on normalized text and entity type for deduplication."""
        return hash((self.normalized_text, self.entity_type))
    
    def __eq__(self, other):
        """Equality based on normalized text and entity type."""
        if not isinstance(other, ExtractedEntity):
            return False
        return self.normalized_text == other.normalized_text and self.entity_type == other.entity_type


class EntityExtractorError(Exception):
    """Custom exception for entity extraction errors."""
    pass


class EntityExtractor:
    """Main entity extraction class using spaCy NLP."""
    
    def __init__(self, config: Optional[EntityExtractorConfig] = None):
        """Initialize entity extractor with configuration.
        
        Args:
            config: Optional configuration object. Uses defaults if not provided.
            
        Raises:
            EntityExtractorError: If spaCy model cannot be loaded
        """
        self.config = config or EntityExtractorConfig()
        self.nlp = None
        self._load_model()
        
        logger.info(f"Initialized EntityExtractor with config: {self.config}")
        logger.info(f"Using spaCy model: {self.config.model_name}")
        logger.info(f"Target entity types: {self.config.entity_types}")
    
    def _load_model(self):
        """Load spaCy NLP model."""
        try:
            logger.info(f"Loading spaCy model: {self.config.model_name}")
            self.nlp = spacy.load(self.config.model_name)
            logger.info(f"Successfully loaded model: {self.config.model_name}")
        except Exception as e:
            logger.error(f"Failed to load spaCy model {self.config.model_name}: {e}")
            raise EntityExtractorError(f"Failed to load spaCy model {self.config.model_name}: {e}")
    
    def extract_entities(self, text: str, chunk_id: Optional[str] = None) -> List[ExtractedEntity]:
        """Extract entities from text.
        
        Args:
            text: Input text to process
            chunk_id: Optional chunk identifier for metadata
            
        Returns:
            List of extracted entities
            
        Raises:
            EntityExtractorError: If entity extraction fails
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for entity extraction")
            return []
        
        try:
            logger.debug(f"Extracting entities from text (length: {len(text)} chars)")
            
            # Process text with spaCy
            doc = self.nlp(text)
            
            # Extract entities
            entities = []
            for ent in doc.ents:
                # Filter by entity type
                if ent.label_ not in self.config.entity_types:
                    continue
                
                # Calculate confidence (simplified - in real scenario could use model scores)
                confidence = self._calculate_confidence(ent)
                
                # Skip low confidence entities
                if confidence < self.config.min_confidence:
                    logger.debug(f"Skipping low confidence entity: {ent.text} ({ent.label_}, confidence: {confidence:.2f})")
                    continue
                
                # Get context around entity
                context = self._get_context(doc, ent)
                
                # Normalize entity text
                normalized_text = self._normalize_entity_text(ent.text)
                
                # Create entity object
                extracted_entity = ExtractedEntity(
                    text=ent.text,
                    entity_type=ent.label_,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    confidence=confidence,
                    context=context,
                    normalized_text=normalized_text,
                    metadata={
                        "chunk_id": chunk_id,
                        "spacy_ent_id": ent.ent_id_,
                        "has_vector": ent.has_vector,
                        "vector_norm": ent.vector_norm if ent.has_vector else None,
                        "lemma": ent.lemma_,
                    }
                )
                
                entities.append(extracted_entity)
            
            # Apply max entities limit if specified
            if self.config.max_entities_per_chunk and len(entities) > self.config.max_entities_per_chunk:
                # Sort by confidence and keep top N
                entities.sort(key=lambda e: e.confidence, reverse=True)
                entities = entities[:self.config.max_entities_per_chunk]
                logger.debug(f"Limited entities to top {self.config.max_entities_per_chunk} by confidence")
            
            # Deduplicate entities if enabled
            if self.config.deduplicate_entities:
                entities = self._deduplicate_entities(entities)
            
            logger.info(f"Extracted {len(entities)} entities from text")
            return entities
            
        except Exception as e:
            logger.error(f"Failed to extract entities: {e}")
            raise EntityExtractorError(f"Failed to extract entities: {e}")
    
    def extract_entities_from_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from multiple text chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'id' and 'text' keys
            
        Returns:
            Dictionary mapping chunk_id to list of extracted entities
            
        Raises:
            EntityExtractorError: If entity extraction fails
        """
        results = {}
        
        for chunk in chunks:
            chunk_id = chunk.get('id', 'unknown')
            text = chunk.get('text', '')
            
            try:
                entities = self.extract_entities(text, chunk_id)
                results[chunk_id] = entities
                
                logger.debug(f"Extracted {len(entities)} entities from chunk {chunk_id}")
                
            except Exception as e:
                logger.error(f"Failed to extract entities from chunk {chunk_id}: {e}")
                # Continue with next chunk instead of failing completely
                results[chunk_id] = []
        
        return results
    
    def _calculate_confidence(self, entity: Span) -> float:
        """Calculate confidence score for an entity.
        
        Note: This is a simplified implementation. In production, you might use
        model probabilities or other heuristics.
        
        Args:
            entity: spaCy entity span
            
        Returns:
            Confidence score between 0 and 1
        """
        # Base confidence based on entity type
        type_confidence_map = {
            "PERSON": 0.9,
            "ORG": 0.85,
            "GPE": 0.8,
            "LAW": 0.7,
            "MONEY": 0.9,
            "DATE": 0.95,
            "PERCENT": 0.95,
            "QUANTITY": 0.8,
        }
        
        base_confidence = type_confidence_map.get(entity.label_, 0.5)
        
        # Adjust based on text length (longer entities might be more reliable)
        length_factor = min(len(entity.text.split()), 5) / 5.0  # 0 to 1
        
        # Adjust based on capitalization (proper nouns often capitalized)
        words = entity.text.split()
        if words:
            capitalized_words = sum(1 for word in words if word.istitle())
            capitalization_factor = capitalized_words / len(words)
        else:
            capitalization_factor = 0.5
        
        # Combine factors
        confidence = base_confidence * 0.5 + length_factor * 0.3 + capitalization_factor * 0.2
        
        return min(max(confidence, 0.0), 1.0)
    
    def _get_context(self, doc: Doc, entity: Span, context_words: Optional[int] = None) -> str:
        """Get context around an entity.
        
        Args:
            doc: spaCy document
            entity: Entity span
            context_words: Number of words to include before and after (uses config if None)
            
        Returns:
            Context string with entity highlighted
        """
        if context_words is None:
            context_words = self.config.include_context_words
        
        # Get token indices
        start_token = entity.start - context_words
        end_token = entity.end + context_words
        
        # Bound checks
        start_token = max(start_token, 0)
        end_token = min(end_token, len(doc))
        
        # Extract context tokens
        context_tokens = []
        for i in range(start_token, end_token):
            if i == entity.start:
                context_tokens.append(f"[{entity.text}]")  # Mark entity
            elif entity.start < i < entity.end:
                continue  # Skip remaining tokens of the entity
            else:
                context_tokens.append(doc[i].text)
        
        return " ".join(context_tokens)
    
    def _normalize_entity_text(self, text: str) -> str:
        """Normalize entity text for deduplication.
        
        Args:
            text: Entity text
            
        Returns:
            Normalized text
        """
        if not self.config.normalize_entities:
            return text
        
        # Lowercase and strip
        normalized = text.lower().strip()
        
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        
        # Remove common prefixes/suffixes (simplified)
        for prefix in ["the ", "a ", "an "]:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        return normalized
    
    def _deduplicate_entities(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Remove duplicate entities.
        
        Args:
            entities: List of extracted entities
            
        Returns:
            Deduplicated list of entities
        """
        seen = set()
        deduplicated = []
        
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                deduplicated.append(entity)
            else:
                logger.debug(f"Deduplicated entity: {entity.text} ({entity.entity_type})")
        
        logger.info(f"Deduplicated {len(entities) - len(deduplicated)} entities")
        return deduplicated
    
    def analyze_entity_distribution(self, entities: List[ExtractedEntity]) -> Dict[str, Any]:
        """Analyze distribution of extracted entities.
        
        Args:
            entities: List of extracted entities
            
        Returns:
            Dictionary with analysis results
        """
        distribution = {}
        confidence_scores = []
        
        for entity in entities:
            entity_type = entity.entity_type
            distribution[entity_type] = distribution.get(entity_type, 0) + 1
            confidence_scores.append(entity.confidence)
        
        total_entities = len(entities)
        
        return {
            "total_entities": total_entities,
            "entity_distribution": dict(sorted(distribution.items(), key=lambda x: x[1], reverse=True)),
            "unique_entity_types": len(distribution),
            "average_confidence": sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0,
            "min_confidence": min(confidence_scores) if confidence_scores else 0,
            "max_confidence": max(confidence_scores) if confidence_scores else 0,
        }
    
    def get_entity_statistics(self, text: str) -> Dict[str, Any]:
        """Get statistics about entities in text.
        
        Args:
            text: Input text
            
        Returns:
            Dictionary with entity statistics
        """
        entities = self.extract_entities(text)
        return self.analyze_entity_distribution(entities)
    
    @classmethod
    def create_default_extractor(cls) -> 'EntityExtractor':
        """Create an extractor with default configuration.
        
        Returns:
            EntityExtractor instance with default config
        """
        return cls(EntityExtractorConfig())


def main():
    """Example usage and testing of entity extractor."""
    import sys
    
    # Sample regulatory text for testing
    sample_text = """
    The Hong Kong Monetary Authority (HKMA) announced new Basel III capital requirements.
    Banks must maintain a minimum Common Equity Tier 1 (CET1) ratio of 4.5% by January 2025.
    John Smith, CEO of Standard Chartered Bank, stated that the regulations will improve financial stability.
    The Financial Services Development Council (FSDC) supports these measures.
    """
    
    print("Testing Entity Extractor...")
    print("=" * 60)
    print(f"Sample text:\n{sample_text}")
    print("=" * 60)
    
    try:
        # Create extractor
        extractor = EntityExtractor.create_default_extractor()
        
        # Extract entities
        print("\nExtracting entities...")
        entities = extractor.extract_entities(sample_text, chunk_id="test-chunk-001")
        
        # Display results
        print(f"\nExtracted {len(entities)} entities:")
        for i, entity in enumerate(entities, 1):
            print(f"\n{i}. {entity.text} ({entity.entity_type})")
            print(f"   Confidence: {entity.confidence:.2f}")
            print(f"   Context: {entity.context}")
            print(f"   Position: chars {entity.start_char}-{entity.end_char}")
            print(f"   Normalized: {entity.normalized_text}")
        
        # Analyze distribution
        print("\n" + "=" * 60)
        print("Entity Analysis:")
        analysis = extractor.analyze_entity_distribution(entities)
        
        print(f"Total entities: {analysis['total_entities']}")
        print(f"Unique entity types: {analysis['unique_entity_types']}")
        print(f"Average confidence: {analysis['average_confidence']:.2f}")
        
        print("\nEntity distribution:")
        for entity_type, count in analysis['entity_distribution'].items():
            print(f"  {entity_type}: {count}")
        
        # Test with multiple chunks
        print("\n" + "=" * 60)
        print("Testing batch extraction...")
        
        chunks = [
            {"id": "chunk1", "text": "The Basel III framework was developed by the Basel Committee."},
            {"id": "chunk2", "text": "HKMA implements regulations in Hong Kong SAR."},
            {"id": "chunk3", "text": "Minimum capital requirements are set at 8%."},
        ]
        
        batch_results = extractor.extract_entities_from_chunks(chunks)
        
        for chunk_id, chunk_entities in batch_results.items():
            print(f"Chunk {chunk_id}: {len(chunk_entities)} entities")
        
        print("\n✅ Entity extractor test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

