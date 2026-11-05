"""
Tests for the HybridRouter component.

Demonstrates Kiro's automated testing hook functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from src.config import QueryType
from src.models import QueryRequest
from src.router import HybridRouter


class TestHybridRouter:
    """Test suite for HybridRouter."""
    
    @pytest.fixture
    def router(self):
        """Create a HybridRouter instance for testing."""
        return HybridRouter()
    
    @pytest.fixture
    def sample_query(self):
        """Create a sample query request."""
        return QueryRequest(
            query="What are the capital requirements for banks?",
            query_type=QueryType.REGULATORY,
            max_results=5,
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, router):
        """Test that router initializes correctly."""
        assert router is not None
        assert router.logger is not None
    
    @pytest.mark.asyncio
    async def test_classify_intent_with_provided_type(self, router, sample_query):
        """Test intent classification when query_type is provided."""
        query_type = await router._classify_intent(sample_query)
        assert query_type == QueryType.REGULATORY
    
    @pytest.mark.asyncio
    async def test_classify_intent_auto_detection(self, router):
        """Test automatic intent classification."""
        # Test entity relationship query
        entity_query = QueryRequest(query="What subsidiaries does Bank of America own?")
        entity_type = await router._classify_intent(entity_query)
        assert entity_type == QueryType.ENTITY_RELATIONSHIP
        
        # Test regulatory query
        regulatory_query = QueryRequest(query="Basel III capital requirements")
        regulatory_type = await router._classify_intent(regulatory_query)
        assert regulatory_type == QueryType.REGULATORY
        
        # Test semantic query
        semantic_query = QueryRequest(query="Explain quantitative easing")
        semantic_type = await router._classify_intent(semantic_query)
        assert semantic_type == QueryType.SEMANTIC
        
        # Test hybrid query (default)
        hybrid_query = QueryRequest(query="Tell me about finance")
        hybrid_type = await router._classify_intent(hybrid_query)
        assert hybrid_type == QueryType.HYBRID
    
    def test_determine_alpha_provided(self, router, sample_query):
        """Test alpha determination when alpha is provided."""
        sample_query.alpha = 0.7
        alpha = router._determine_alpha(sample_query, QueryType.REGULATORY)
        assert alpha == 0.7
    
    def test_determine_alpha_default(self, router, sample_query):
        """Test alpha determination using defaults."""
        # Test different query types
        entity_alpha = router._determine_alpha(sample_query, QueryType.ENTITY_RELATIONSHIP)
        regulatory_alpha = router._determine_alpha(sample_query, QueryType.REGULATORY)
        semantic_alpha = router._determine_alpha(sample_query, QueryType.SEMANTIC)
        hybrid_alpha = router._determine_alpha(sample_query, QueryType.HYBRID)
        
        assert entity_alpha == 0.8
        assert regulatory_alpha == 0.7
        assert semantic_alpha == 0.3
        assert hybrid_alpha == 0.5
    
    @pytest.mark.asyncio
    async def test_parallel_retrieval(self, router, sample_query):
        """Test parallel retrieval execution."""
        graph_results, vector_results = await router._parallel_retrieval(sample_query)
        
        assert isinstance(graph_results, list)
        assert isinstance(vector_results, list)
        assert len(graph_results) > 0
        assert len(vector_results) > 0
        
        # Check result structure
        for result in graph_results:
            assert hasattr(result, 'content')
            assert hasattr(result, 'source')
            assert hasattr(result, 'score')
            assert result.source.value == 'graph'
        
        for result in vector_results:
            assert hasattr(result, 'content')
            assert hasattr(result, 'source')
            assert hasattr(result, 'score')
            assert result.source.value == 'vector'
    
    @pytest.mark.asyncio
    async def test_fuse_results(self, router, sample_query):
        """Test result fusion with different alpha values."""
        # Get mock results
        graph_results, vector_results = await router._parallel_retrieval(sample_query)
        
        # Test with high alpha (graph-weighted)
        high_alpha_results = await router._fuse_results(
            graph_results, vector_results, alpha=0.8
        )
        assert len(high_alpha_results) > 0
        
        # Test with low alpha (vector-weighted)
        low_alpha_results = await router._fuse_results(
            graph_results, vector_results, alpha=0.2
        )
        assert len(low_alpha_results) > 0
        
        # Test that fusion produces hybrid source type
        for result in high_alpha_results:
            assert result.source.value == 'hybrid'
    
    @pytest.mark.asyncio
    async def test_build_context(self, router, sample_query):
        """Test context building from results."""
        graph_results, vector_results = await router._parallel_retrieval(sample_query)
        fused_results = await router._fuse_results(graph_results, vector_results, alpha=0.5)
        
        context = await router._build_context(fused_results, sample_query)
        
        assert isinstance(context, str)
        assert len(context) > 0
        assert sample_query.query in context
        
        # Check that results are included
        for result in fused_results[:2]:  # Check first two results
            assert result.content in context
    
    @pytest.mark.asyncio
    async def test_generate_response(self, router, sample_query):
        """Test response generation."""
        graph_results, vector_results = await router._parallel_retrieval(sample_query)
        fused_results = await router._fuse_results(graph_results, vector_results, alpha=0.5)
        context = await router._build_context(fused_results, sample_query)
        
        answer, confidence = await router._generate_response(context, sample_query)
        
        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(confidence, float)
        assert 0 <= confidence <= 1
    
    @pytest.mark.asyncio
    async def test_full_retrieval_pipeline(self, router, sample_query):
        """Test the complete retrieval pipeline."""
        response = await router.retrieve(sample_query)
        
        # Check response structure
        assert hasattr(response, 'answer')
        assert hasattr(response, 'sources')
        assert hasattr(response, 'confidence')
        assert hasattr(response, 'query_type')
        
        # Validate types and values
        assert isinstance(response.answer, str)
        assert len(response.answer) > 0
        assert isinstance(response.sources, list)
        assert isinstance(response.confidence, float)
        assert 0 <= response.confidence <= 1
        assert response.query_type == QueryType.REGULATORY
        
        # Check that we have sources
        assert len(response.sources) > 0
    
    @pytest.mark.asyncio
    async def test_health_check(self, router):
        """Test health check functionality."""
        health = await router.health_check()
        
        assert isinstance(health, dict)
        assert 'intent_classifier' in health
        assert 'graph_store' in health
        assert 'vector_store' in health
    
    @pytest.mark.asyncio
    async def test_error_handling(self, router):
        """Test error handling in the pipeline."""
        # Test with empty query (should still work, just return minimal response)
        empty_query = QueryRequest(query="")
        response = await router.retrieve(empty_query)
        assert response is not None
        assert len(response.answer) > 0
        
        # Test with very long query (should still work)
        long_query = QueryRequest(query="A" * 1000)
        response = await router.retrieve(long_query)
        assert response is not None


class TestPerformance:
    """Performance tests for HybridRouter."""
    
    @pytest.fixture
    def router(self):
        """Create a HybridRouter instance for performance testing."""
        return HybridRouter()
    
    @pytest.mark.asyncio
    async def test_retrieval_latency(self, router):
        """Test that retrieval completes within reasonable time."""
        query = QueryRequest(
            query="What are the capital requirements for banks under Basel III?",
            max_results=10,
        )
        
        import time
        start_time = time.time()
        response = await router.retrieve(query)
        end_time = time.time()
        
        processing_time = end_time - start_time
        assert processing_time < 5.0, f"Retrieval took {processing_time:.2f}s, expected <5s"
        
        # Also check that processing_time is set
        assert response.processing_time > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_queries(self, router):
        """Test handling multiple concurrent queries."""
        queries = [
            QueryRequest(query="Basel III requirements"),
            QueryRequest(query="Bank subsidiaries"),
            QueryRequest(query="Quantitative easing explanation"),
        ]
        
        # Process queries concurrently
        tasks = [router.retrieve(query) for query in queries]
        responses = await asyncio.gather(*tasks)
        
        assert len(responses) == len(queries)
        for response in responses:
            assert response is not None
            assert len(response.answer) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])