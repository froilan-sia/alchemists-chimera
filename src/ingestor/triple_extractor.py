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
import math
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from collections import deque

import requests
from requests.adapters import HTTPAdapter
from pydantic import BaseModel, Field, ValidationError
from requests.exceptions import RequestException, Timeout

from ..performance import FileContentCache
from .pdf_parser import PDFChunk
from .entity_extractor import ExtractedEntity

logger = logging.getLogger(__name__)


DEFAULT_OLLAMA_TIMEOUT = 120.0
MIN_OLLAMA_TIMEOUT = 5.0
MAX_OLLAMA_TIMEOUT = 120.0


def _resolve_ollama_timeout() -> float:
    """Resolve the default Ollama timeout from the environment."""
    raw_timeout = os.getenv("OLLAMA_TIMEOUT")
    if raw_timeout is None or not raw_timeout.strip():
        return DEFAULT_OLLAMA_TIMEOUT

    try:
        timeout = float(raw_timeout.strip())
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring invalid OLLAMA_TIMEOUT value %r; using %.1f seconds.",
            raw_timeout,
            DEFAULT_OLLAMA_TIMEOUT,
        )
        return DEFAULT_OLLAMA_TIMEOUT

    if not math.isfinite(timeout) or not MIN_OLLAMA_TIMEOUT <= timeout <= MAX_OLLAMA_TIMEOUT:
        logger.warning(
            "Ignoring out-of-range OLLAMA_TIMEOUT value %r; using %.1f seconds.",
            raw_timeout,
            DEFAULT_OLLAMA_TIMEOUT,
        )
        return DEFAULT_OLLAMA_TIMEOUT
    return timeout


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
        default_factory=_resolve_ollama_timeout,
        ge=MIN_OLLAMA_TIMEOUT,
        le=MAX_OLLAMA_TIMEOUT,
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
    finance_prefix: str = Field(
        default="finance:",
        description="Canonical prefix for ontology classes and properties"
    )
    chimera_prefix: str = Field(
        default="chimera:",
        description="Prefix for project-specific instances and metadata"
    )
    entity_prefix: str = Field(
        default="chimera:",
        description="Backward-compatible fallback prefix for unknown entities"
    )
    predicate_prefix: str = Field(
        default="chimera:", 
        description="Prefix for extracted predicates in triples"
    )
    ontology_path: str = Field(
        default="./ontology/finance-ontology.ttl",
        description="Ontology file used to guide extraction"
    )
    connection_pool_size: int = Field(
        default=1,
        ge=1,
        le=4,
        description="HTTP connections reserved for sequential Ollama inference"
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

        # Reuse a bounded HTTP connection pool.  The pool is intentionally
        # sized for sequential qwen2.5:3b inference, never parallel inference.
        adapter = HTTPAdapter(
            pool_connections=self.config.connection_pool_size,
            pool_maxsize=self.config.connection_pool_size,
            pool_block=True,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.ontology_content = self._load_ontology(self.config.ontology_path)
        self._ontology_terms, self._ontology_labels = self._index_ontology_terms(
            self.ontology_content
        )
        self.pending_extractions = deque()
        self.last_error: Optional[str] = None
        
        # Configure session for better reliability
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AlchemistsChimera/1.0'
        })
        
        logger.info(f"Initialized TripleExtractor with config: {self.config}")
        logger.info(f"Using model: {self.config.model_name} at {self.config.ollama_base_url}")

    @staticmethod
    def _load_ontology(ontology_path: str) -> str:
        """Load ontology text through the shared mtime-aware cache."""
        path = Path(ontology_path)
        if not path.exists():
            logger.warning("Ontology file does not exist: %s", path)
            return ""
        try:
            return FileContentCache.get_text(path)
        except OSError as error:
            logger.warning("Unable to load ontology %s: %s", path, error)
            return ""
    
    @staticmethod
    def _index_ontology_terms(content: str) -> Tuple[Set[str], Dict[str, str]]:
        """Index finance classes/properties and their human-readable labels."""
        terms: Set[str] = set()
        labels: Dict[str, str] = {}
        for match in re.finditer(r"(?:^|[;\s])(?:finance:|:)([A-Za-z][A-Za-z0-9_]*)", content):
            terms.add(match.group(1))
        for match in re.finditer(
            r"(?:finance:|:)([A-Za-z][A-Za-z0-9_]*)[^.]*?rdfs:label\s+\"([^\"]+)\"",
            content,
            flags=re.DOTALL,
        ):
            labels[TripleExtractor._term_key(match.group(2))] = match.group(1)
        return terms, labels

    @staticmethod
    def _term_key(value: str) -> str:
        """Normalize a label for ontology lookup."""
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    @staticmethod
    def _strip_type_suffix(value: str) -> str:
        """Remove entity-extractor type suffixes from concept identifiers."""
        return re.sub(r"_(?:person|org)$", "", value, flags=re.IGNORECASE)

    def _canonical_entity(self, value: str) -> str:
        """Map known finance concepts to ``finance:`` and clean unknown IDs."""
        raw = str(value or "").strip()
        for namespace, prefix in (
            ("http://example.org/finance#", self.config.finance_prefix),
            ("http://example.org/chimera#", self.config.chimera_prefix),
            ("http://alchemists-chimera.org/", self.config.chimera_prefix),
        ):
            if raw.startswith(namespace):
                raw = f"{prefix}{raw[len(namespace):]}"
                break
        if ":" in raw and not raw.startswith(("http://", "https://")):
            prefix, local = raw.split(":", 1)
            if prefix in {"finance", "chimera"}:
                raw = f"{prefix}:{local}"
            else:
                raw = f"{self.config.chimera_prefix}{local}"
        else:
            raw = f"{self.config.chimera_prefix}{raw}"

        prefix, local = raw.split(":", 1)
        local = self._strip_type_suffix(local)
        clean_local = re.sub(r"[^A-Za-z0-9]+", "_", local).strip("_")
        clean_local = re.sub(r"(?:_\d+)+$", "", clean_local)
        key = self._term_key(clean_local)
        canonical_local = next(
            (term for term in self._ontology_terms if self._term_key(term) == key),
            self._ontology_labels.get(key),
        )
        # Common plural wording in regulatory text maps to the singular class.
        if canonical_local is None and key.endswith("s"):
            canonical_local = self._ontology_labels.get(key[:-1]) or next(
                (term for term in self._ontology_terms if self._term_key(term) == key[:-1]),
                None,
            )
        if canonical_local:
            return f"{self.config.finance_prefix}{canonical_local}"
        if prefix == self.config.finance_prefix.rstrip(":"):
            return f"{self.config.finance_prefix}{clean_local}"
        return f"{self.config.chimera_prefix}{clean_local}"

    def _canonical_predicate(self, value: str) -> str:
        """Map known ontology properties and keep unknown relations in Chimera."""
        raw = str(value or "").strip()
        if raw.startswith("http://example.org/finance#"):
            raw = raw.rsplit("#", 1)[-1]
        elif raw.startswith("finance:"):
            raw = raw.split(":", 1)[1]
        elif raw.startswith("chimera:"):
            raw = raw.split(":", 1)[1]
        local = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
        key = self._term_key(local)
        canonical = next(
            (term for term in self._ontology_terms if self._term_key(term) == key),
            self._ontology_labels.get(key),
        )
        if canonical and canonical in self._ontology_terms:
            return f"{self.config.finance_prefix}{canonical}"
        return f"{self.config.chimera_prefix}{local or 'relatedTo'}"
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
            
        except TripleExtractorError as error:
            self.last_error = str(error)
            self.queue_extraction(chunk, entities)
            logger.error("Ollama unavailable for chunk %s; deferred extraction: %s", chunk.id, error)
            return self._create_fallback_triples(chunk, entities), ExtractionStatus.FAILED
        except Exception as e:
            self.last_error = str(e)
            logger.error("Failed to extract triples from chunk %s: %s", chunk.id, e, exc_info=True)
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
- Use the canonical finance namespace for concepts/classes/properties known by the ontology.
- Use the chimera namespace only for source-specific instances, extraction metadata, or unknown entities.
- Never use rdf:, rdfs:, owl:, xsd:, or a type suffix such as _person/_org for a financial concept.
- Do not invent entities from anchor suffixes. The ``_ORG``/``_PERSON`` text in an anchor is type context only.
- Preserve ontology spellings such as finance:BaselIII and finance:CapitalRequirement.
- Return numeric values and quoted measurements as plain object values when appropriate.
- Evidence must be an exact substring from the original text
- Maximum {self.config.max_triples_per_chunk} triples

Example response format:
[
  {{
    "subject": "finance:BaselCommittee",
    "predicate": "finance:subjectTo",
    "object": "finance:BaselIII",
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
                
                logger.debug("Successfully received response from Ollama")
                self.last_error = None
                return data
                
            except Exception as e:
                self.last_error = str(e)
                logger.warning("Ollama API call failed (attempt %s/%s): %s", attempt + 1, self.config.max_retries + 1, e)
                
                if attempt < self.config.max_retries:
                    # Exponential backoff: base, 2*base, 4*base, ...
                    delay = self.config.retry_delay_base * (2 ** attempt)
                    logger.info("Retrying Ollama request in %.1f seconds", delay)
                    time.sleep(delay)
                else:
                    logger.error("All %s Ollama attempts failed", self.config.max_retries + 1)
                    raise TripleExtractorError(
                        f"Failed to call Ollama API after {self.config.max_retries + 1} attempts: {e}"
                    ) from e
    
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
                    
                    # Normalize every term against the ontology. This is the
                    # final guard against LLM-generated _person/_org concepts
                    # and fallback chimera entities for known finance terms.
                    subject = self._canonical_entity(subject)
                    predicate = self._canonical_predicate(predicate)
                    obj = self._canonical_entity(obj)
                    
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
        
        # Remove any known prefix and extraction type suffix for matching.
        subject_clean = re.sub(r"^(?:finance|chimera):", "", subject)
        obj_clean = re.sub(r"^(?:finance|chimera):", "", obj)
        subject_clean = self._strip_type_suffix(subject_clean)
        obj_clean = self._strip_type_suffix(obj_clean)
        
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
                    subject = self._canonical_entity(entities[i].normalized_text)
                    object = self._canonical_entity(entities[j].normalized_text)
                    
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
    
    def queue_extraction(self, chunk: PDFChunk, entities: Optional[List[ExtractedEntity]] = None) -> None:
        """Queue a chunk for retryable extraction when Ollama is unavailable."""
        self.pending_extractions.append((chunk, entities or []))
        logger.warning("Queued chunk %s for deferred Ollama extraction", chunk.id)

    def process_pending_extractions(self) -> Dict[str, Tuple[List[ExtractedTriple], ExtractionStatus]]:
        """Drain queued extraction work, retaining failures for a later retry."""
        results: Dict[str, Tuple[List[ExtractedTriple], ExtractionStatus]] = {}
        pending = list(self.pending_extractions)
        self.pending_extractions.clear()
        for chunk, entities in pending:
            try:
                results[chunk.id] = self.extract_triples_from_chunk(chunk, entities)
            except TripleExtractorError:
                self.pending_extractions.append((chunk, entities))
                results[chunk.id] = ([], ExtractionStatus.FAILED)
        return results

    def health_check(self) -> Dict[str, Any]:
        """Check Ollama reachability without raising into monitoring callers."""
        healthy = self.test_ollama_connection()
        return {
            "status": "healthy" if healthy else "degraded",
            "component": "triple_extractor",
            "ollama_url": self.config.ollama_base_url,
            "model": self.config.model_name,
            "queued_extractions": len(self.pending_extractions),
            "last_error": self.last_error,
        }

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
