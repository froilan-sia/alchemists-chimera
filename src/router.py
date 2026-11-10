"""
Hybrid router for Alchemist's Chimera.

Orchestrates the full hybrid retrieval pipeline:
1. Intent classification
2. Parallel graph/vector retrieval
3. Result fusion
4. Context building
5. LLM response generation
"""

import asyncio
import logging
from typing import Optional

from .config import settings, QueryType
from .models import QueryRequest, HybridResponse, RetrievalResult, RetrievalSource

from .graph_store import get_graph_store
from .vector_store import get_vector_store
from .fusion import get_fusion_engine
from .intent_classifier import IntentClassifier
from .context_builder import ContextBuilder
from .response_generator import ResponseGenerator

logger = logging.getLogger(__name__)


class HybridRouter:
    """Main orchestrator for hybrid retrieval pipeline."""
    
    def __init__(self, graph_store=None, vector_store=None, fusion_engine=None, 
                 intent_classifier=None, context_builder=None, response_generator=None, 
                 use_mocks=False):
        """Initialize hybrid router with component dependencies.
        
        Args:
            graph_store: GraphStore instance for knowledge graph retrieval
            vector_store: VectorStore instance for semantic vector search
            fusion_engine: FusionEngine instance for result fusion
            intent_classifier: IntentClassifier instance for query type detection
            context_builder: ContextBuilder instance for context assembly
            response_generator: ResponseGenerator instance for answer generation
            use_mocks: If True, use mock implementations instead of real components
        """
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing HybridRouter")
        
        # Store configuration
        self.use_mocks = use_mocks
        
        # Initialize components
        if use_mocks:
            self.logger.info("Using mock implementations")
            self.graph_store = None
            self.vector_store = None
            self.fusion_engine = None
            self.intent_classifier = None
            self.context_builder = None
            self.response_generator = None
        else:
            # Use provided components or get default singletons
            self.graph_store = graph_store or get_graph_store()
            self.vector_store = vector_store or get_vector_store()
            self.fusion_engine = fusion_engine or get_fusion_engine()
            
            # These components will be implemented later
            self.intent_classifier = intent_classifier
            self.context_builder = context_builder
            self.response_generator = response_generator
            
            self.logger.info(f"Initialized with real components: "
                           f"graph_store={self.graph_store is not None}, "
                           f"vector_store={self.vector_store is not None}, "
                           f"fusion_engine={self.fusion_engine is not None}")
        
        self.logger.info("HybridRouter initialized")
    async def retrieve(self, request: QueryRequest) -> HybridResponse:
        """
        Execute full hybrid retrieval pipeline.
        
        Args:
            request: Query request with metadata
            
        Returns:
            Hybrid response with answer and sources
        """
        self.logger.info(f"Processing query: {request.query[:50]}...")
        
        import time
        start_time = time.time()
        
        try:
            # 1. Classify query intent
            query_type = await self._classify_intent(request)
            
            # 2. Determine alpha parameter
            alpha = self._determine_alpha(request, query_type)
            
            # 3. Execute parallel retrieval
            graph_results, vector_results = await self._parallel_retrieval(request)
            
            # 4. Fuse results
            fused_results = await self._fuse_results(
                graph_results, vector_results, alpha
            )
            
            # 5. Build context for LLM
            context = await self._build_context(fused_results, request)
            
            # 6. Generate response
            answer, confidence = await self._generate_response(context, request)
            
            processing_time = time.time() - start_time
            
            # Create response
            response = HybridResponse(
                answer=answer,
                sources=fused_results,
                confidence=confidence,
                query_type=query_type,
                processing_time=processing_time,
            )
            
            self.logger.info(
                f"Query processed successfully in {processing_time:.2f}s. "
                f"Type: {query_type}, Alpha: {alpha}, "
                f"Results: {len(fused_results)}, Confidence: {confidence:.2f}"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error in retrieval pipeline: {e}", exc_info=True)
            raise
    
    async def _classify_intent(self, request: QueryRequest) -> QueryType:
        """Classify query intent and type."""
        # Use provided query_type if available
        if request.query_type:
            self.logger.debug(f"Using provided query type: {request.query_type}")
            return request.query_type
        
        # Otherwise, classify automatically
        self.logger.debug("Classifying query intent automatically")
        
        # Simple rule-based classification for now
        query_lower = request.query.lower()
        
        # Check for entity relationship queries
        entity_keywords = ["subsidiary", "subsidiaries", "owns", "owned by", "parent company"]
        if any(keyword in query_lower for keyword in entity_keywords):
            return QueryType.ENTITY_RELATIONSHIP
        
        # Check for regulatory queries
        regulatory_keywords = ["regulation", "compliance", "requirement", "standard", "basel", "capital"]
        if any(keyword in query_lower for keyword in regulatory_keywords):
            return QueryType.REGULATORY
        
        # Check for semantic/conceptual queries
        semantic_keywords = ["explain", "describe", "how does", "what is", "concept"]
        if any(keyword in query_lower for keyword in semantic_keywords):
            return QueryType.SEMANTIC
        
        # Default to hybrid
        return QueryType.HYBRID
    
    def _determine_alpha(self, request: QueryRequest, query_type: QueryType) -> float:
        """Determine alpha parameter for fusion."""
        # Use provided alpha if available
        if request.alpha is not None:
            self.logger.debug(f"Using provided alpha: {request.alpha}")
            return request.alpha
        
        # Otherwise, use default based on query type
        alpha = settings.default_alpha.get(query_type, 0.5)
        self.logger.debug(f"Using default alpha for {query_type}: {alpha}")
        return alpha
    
    async def _parallel_retrieval(
        self, request: QueryRequest
    ) -> tuple[list[RetrievalResult], list[RetrievalResult]]:
        """Execute parallel retrieval from graph and vector stores."""
        self.logger.debug("Starting parallel retrieval")
        
        if self.use_mocks:
            # Use mock implementations for testing
            self.logger.debug("Using mock implementations for retrieval")
            graph_results = await self._mock_graph_retrieval(request)
            vector_results = await self._mock_vector_retrieval(request)
        else:
            # Use real components
            if not self.graph_store or not self.vector_store:
                raise RuntimeError(
                    "GraphStore or VectorStore not initialized. "
                    "Ensure components are provided or set use_mocks=True."
                )
            
            self.logger.debug("Using real components for retrieval")
            
            # Execute retrieval concurrently
            import asyncio
            try:
                # For now, use synchronous calls since GraphStore.retrieve is not async
                # In the future, these should be made async
                                # Try to extract entities from query for graph search
                # For now, use retrieve_by_entity with the query as entity name
                # In a real implementation, we'd have proper entity extraction
                try:
                    graph_results = self.graph_store.retrieve_by_entity(
                        request.query, request.max_results
                    )
                except Exception as graph_error:
                    self.logger.warning(f"Graph store error: {graph_error}. Using mock fallback.")
                    graph_results = await self._mock_graph_retrieval(request)
                vector_results = self.vector_store.retrieve(request.query, request.max_results)
            except Exception as e:
                self.logger.error(f"Error during retrieval: {e}")
                # Fall back to mock implementations if real components fail
                self.logger.warning("Falling back to mock implementations")
                graph_results = await self._mock_graph_retrieval(request)
                vector_results = await self._mock_vector_retrieval(request)
        
        self.logger.debug(
            f"Retrieved {len(graph_results)} graph results, "
            f"{len(vector_results)} vector results"
        )
        
        return graph_results, vector_results
    
    async def _mock_graph_retrieval(self, request: QueryRequest) -> list[RetrievalResult]:
        """Mock graph retrieval for development."""
        # This will be replaced with actual RDFLib/SPARQL implementation
        await asyncio.sleep(0.1)  # Simulate network delay
        
        return [
            RetrievalResult(
                content="Sample graph retrieval result 1. This demonstrates entity relationships from the knowledge graph.",
                source=RetrievalSource.GRAPH,
                score=0.85,
                metadata={"type": "mock", "component": "graph_store"},
                entity_links=["http://example.org/finance#Entity1"],
            ),
            RetrievalResult(
                content="Sample graph retrieval result 2. Regulatory information from structured data.",
                source=RetrievalSource.GRAPH,
                score=0.72,
                metadata={"type": "mock", "component": "graph_store"},
                entity_links=["http://example.org/finance#Regulation1"],
            ),
        ]
    
    async def _mock_vector_retrieval(self, request: QueryRequest) -> list[RetrievalResult]:
        """Mock vector retrieval for development."""
        # This will be replaced with actual ChromaDB implementation
        await asyncio.sleep(0.1)  # Simulate network delay
        
        return [
            RetrievalResult(
                content="Sample vector retrieval result 1. This shows semantic similarity matching from document embeddings.",
                source=RetrievalSource.VECTOR,
                score=0.78,
                metadata={"type": "mock", "component": "vector_store"},
            ),
            RetrievalResult(
                content="Sample vector retrieval result 2. Contextual information from unstructured documents.",
                source=RetrievalSource.VECTOR,
                score=0.65,
                metadata={"type": "mock", "component": "vector_store"},
            ),
        ]
    
    async def _fuse_results(
        self,
        graph_results: list[RetrievalResult],
        vector_results: list[RetrievalResult],
        alpha: float,
    ) -> list[RetrievalResult]:
        """Fuse graph and vector results using configured strategy."""
        self.logger.debug(f"Fusing results with alpha={alpha}")
        
        if self.use_mocks or not self.fusion_engine:
            # Use inline fusion for mocks or if fusion engine is not available
            self.logger.debug("Using inline fusion (mock mode or no fusion engine)")
            
            # Simple weighted fusion for now
            fused = []
            
            # Process graph results with alpha weight
            for result in graph_results:
                fused_score = result.score * alpha
                fused.append(
                    RetrievalResult(
                        content=result.content,
                        source=RetrievalSource.HYBRID,
                        score=fused_score,
                        metadata={**result.metadata, "fusion_weight": alpha},
                        entity_links=result.entity_links,
                    )
                )
            
            # Process vector results with (1-alpha) weight
            for result in vector_results:
                fused_score = result.score * (1 - alpha)
                fused.append(
                    RetrievalResult(
                        content=result.content,
                        source=RetrievalSource.HYBRID,
                        score=fused_score,
                        metadata={**result.metadata, "fusion_weight": 1 - alpha},
                    )
                )
            
            # Sort by fused score
            fused.sort(key=lambda x: x.score, reverse=True)
            
            # Limit to requested number
            max_results = 10  # Default, will come from request
            fused = fused[:max_results]
        else:
            # Use FusionEngine
            self.logger.debug("Using FusionEngine for fusion")
            try:
                fused = self.fusion_engine.fuse(graph_results, vector_results, alpha)
            except Exception as e:
                self.logger.error(f"Error in fusion engine: {e}")
                self.logger.warning("Falling back to inline fusion")
                # Fall back to inline fusion
                return await self._fuse_results(graph_results, vector_results, alpha)
        
        self.logger.debug(f"Fused to {len(fused)} results")
        return fused
    
    async def _build_context(
        self, results: list[RetrievalResult], request: QueryRequest
    ) -> str:
        """Build context for LLM from retrieved results."""
        self.logger.debug("Building LLM context")
        
        # Simple context building for now
        context_parts = [f"Query: {request.query}\n\nRelevant information:\n"]
        
        for i, result in enumerate(results, 1):
            source_type = "Graph" if result.entity_links else "Vector"
            context_parts.append(f"[{i}] {source_type} source (score: {result.score:.2f}):")
            context_parts.append(f"{result.content}\n")
        
        return "\n".join(context_parts)
    
    async def _generate_response(
        self, context: str, request: QueryRequest
    ) -> tuple[str, float]:
        """Generate response using LLM."""
        self.logger.debug("Generating LLM response")
        
        # Mock LLM response for now
        await asyncio.sleep(0.2)  # Simulate LLM processing
        
        # Simple mock response based on query
        if "capital" in request.query.lower() and "bank" in request.query.lower():
            answer = "Based on the retrieved information, banks are required to maintain minimum capital ratios under regulatory frameworks like Basel III. The specific requirements depend on the jurisdiction and the bank's risk profile."
            confidence = 0.88
        elif "subsidiary" in request.query.lower():
            answer = "The retrieved information shows corporate subsidiary relationships in the financial sector. Specific ownership structures would require querying the knowledge graph for entity relationships."
            confidence = 0.82
        else:
            answer = "I've analyzed the retrieved information related to your query. The hybrid retrieval system found both structured graph data and unstructured document content relevant to your question."
            confidence = 0.75
        
        self.logger.debug(f"Generated response with confidence {confidence:.2f}")
        return answer, confidence
    
    async def health_check(self) -> dict[str, str]:
        """Check health of all components."""
        health = {}
        
        try:
            # Check intent classifier
            if self.intent_classifier:
                if hasattr(self.intent_classifier, 'health_check'):
                    health["intent_classifier"] = await self.intent_classifier.health_check()
                else:
                    health["intent_classifier"] = "initialized"
            else:
                health["intent_classifier"] = "not_initialized"
        except Exception as e:
            health["intent_classifier"] = f"error: {str(e)}"
        
        try:
            # Check graph store
            if self.graph_store:
                if hasattr(self.graph_store, 'health_check'):
                    graph_health = self.graph_store.health_check()
                    health["graph_store"] = graph_health.get("status", "healthy")
                else:
                    health["graph_store"] = "initialized"
            else:
                health["graph_store"] = "not_initialized"
        except Exception as e:
            health["graph_store"] = f"error: {str(e)}"
        
        try:
            # Check vector store
            if self.vector_store:
                if hasattr(self.vector_store, 'health_check'):
                    vector_health = self.vector_store.health_check()
                    health["vector_store"] = vector_health.get("status", "healthy")
                else:
                    health["vector_store"] = "initialized"
            else:
                health["vector_store"] = "not_initialized"
        except Exception as e:
            health["vector_store"] = f"error: {str(e)}"
        
        try:
            # Check fusion engine
            if self.fusion_engine:
                health["fusion_engine"] = "initialized"
            else:
                health["fusion_engine"] = "not_initialized"
        except Exception as e:
            health["fusion_engine"] = f"error: {str(e)}"
        
        try:
            # Check context builder
            if self.context_builder:
                health["context_builder"] = "initialized"
            else:
                health["context_builder"] = "not_initialized"
        except Exception as e:
            health["context_builder"] = f"error: {str(e)}"
        
        try:
            # Check response generator
            if self.response_generator:
                health["response_generator"] = "initialized"
            else:
                health["response_generator"] = "not_initialized"
        except Exception as e:
            health["response_generator"] = f"error: {str(e)}"
        
        # Overall status
        healthy_count = sum(1 for v in health.values() if "healthy" in v or "initialized" in v)
        total_count = len(health)
        health["overall"] = f"{healthy_count}/{total_count} components healthy"
        
        return health