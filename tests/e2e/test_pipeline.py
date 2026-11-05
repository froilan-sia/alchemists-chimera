#!/usr/bin/env python3
"""
End-to-End Tests for Alchemist's Chimera Hybrid RAG Pipeline

This module tests the complete query processing pipeline from user input
to final response generation.
"""

import asyncio
import pytest
from typing import List

import sys
sys.path.insert(0, '/Users/froilansia/git/alchemists-chimera')

from src.models import QueryRequest, QueryType, RetrievalResult, RetrievalSource, HybridResponse
from src.router import HybridRouter


class TestE2EPipeline:
    """End-to-end pipeline tests."""
    
    @pytest.fixture
    def router(self):
        """Create a HybridRouter instance for testing."""
        return HybridRouter()
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_for_regulatory_query(self, router):
        """Test complete pipeline for regulatory query."""
        # Given: A regulatory query
        query = "What are the capital requirements for banks under Basel III?"
        request = QueryRequest(
            query=query,
            query_type=QueryType.REGULATORY,
            max_results=5,
        )
        
        # When: Processing the query
        response = await router.retrieve(request)
        
        # Then: Response should have all required fields
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.query_type == QueryType.REGULATORY
        assert 0 <= response.confidence <= 1
        assert response.processing_time > 0
        assert len(response.sources) > 0
        
        # Verify source types
        source_types = set(s.source for s in response.sources)
        assert RetrievalSource.HYBRID in source_types
        
        # Verify sources have required fields
        for source in response.sources:
            assert len(source.content) > 0
            assert 0 <= source.score <= 1
            assert source.source == RetrievalSource.HYBRID
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_for_entity_query(self, router):
        """Test complete pipeline for entity relationship query."""
        # Given: An entity relationship query
        query = "What subsidiaries does Bank of America own?"
        request = QueryRequest(
            query=query,
            query_type=QueryType.ENTITY_RELATIONSHIP,
            alpha=0.8,
            max_results=5,
        )
        
        # When: Processing the query
        response = await router.retrieve(request)
        
        # Then: Response should be complete
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.query_type == QueryType.ENTITY_RELATIONSHIP
        assert response.confidence > 0
        
        # Verify alpha weighting was applied
        assert any(hasattr(s, 'metadata') and 'fusion_weight' in s.metadata for s in response.sources)
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_for_semantic_query(self, router):
        """Test complete pipeline for semantic query."""
        # Given: A semantic query
        query = "Explain quantitative easing and its impact on inflation"
        request = QueryRequest(
            query=query,
            query_type=QueryType.SEMANTIC,
            alpha=0.3,
            max_results=5,
        )
        
        # When: Processing the query
        response = await router.retrieve(request)
        
        # Then: Response should be complete
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.query_type == QueryType.SEMANTIC
        assert response.confidence > 0
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_for_hybrid_query(self, router):
        """Test complete pipeline for hybrid query (mixed intent)."""
        # Given: A hybrid query
        query = "How did Apple's stock performance after their last earnings call?"
        request = QueryRequest(
            query=query,
            query_type=QueryType.HYBRID,
            alpha=0.5,
            max_results=5,
        )
        
        # When: Processing the query
        response = await router.retrieve(request)
        
        # Then: Response should be complete
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.query_type == QueryType.HYBRID
        assert response.confidence > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_different_alpha_values(self, router):
        """Test pipeline with different alpha weights."""
        query = "What are the regulatory requirements for banks?"
        
        alpha_values = [0.2, 0.5, 0.8]
        responses = []
        
        for alpha in alpha_values:
            request = QueryRequest(query=query, alpha=alpha, max_results=5)
            response = await router.retrieve(request)
            responses.append(response)
            
            # Verify each response has expected structure
            assert isinstance(response, HybridResponse)
            assert len(response.sources) > 0
        
        # All responses should have sources
        for response in responses:
            assert len(response.sources) > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_query(self, router):
        """Test pipeline handles empty query gracefully."""
        # Given: Empty query
        request = QueryRequest(query="", max_results=5)
        
        # When: Processing the query (should not raise exception)
        response = await router.retrieve(request)
        
        # Then: Should return a valid response
        assert isinstance(response, HybridResponse)
        assert len(response.answer) >= 0  # Empty answer is acceptable
    
    @pytest.mark.asyncio
    async def test_pipeline_with_long_query(self, router):
        """Test pipeline handles long queries."""
        # Given: Very long query
        long_query = "What " * 100 + "regulatory requirements for banks under Basel III?"
        request = QueryRequest(query=long_query, max_results=5)
        
        # When: Processing the long query
        response = await router.retrieve(request)
        
        # Then: Response should still be valid
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.confidence > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_concurrent_queries(self, router):
        """Test pipeline handles multiple concurrent queries."""
        # Given: Multiple queries
        queries = [
            "What are the capital requirements for banks?",
            "What subsidiaries does Bank of America own?",
            "Explain quantitative easing",
        ]
        request_list = [QueryRequest(query=q, max_results=3) for q in queries]
        
        # When: Processing queries concurrently
        responses = await asyncio.gather(*[router.retrieve(req) for req in request_list])
        
        # Then: All responses should be valid
        assert len(responses) == len(queries)
        
        for response in responses:
            assert isinstance(response, HybridResponse)
            assert len(response.answer) > 0
            assert response.confidence > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_preserves_query_type(self, router):
        """Test pipeline preserves query type information."""
        query_types = [
            (QueryType.ENTITY_RELATIONSHIP, "subsidiary"),
            (QueryType.REGULATORY, "capital requirements"),
            (QueryType.SEMANTIC, "explain"),
            (QueryType.HYBRID, "performance"),
        ]
        
        for expected_type, keyword in query_types:
            query = f"What {keyword} for banks?"
            request = QueryRequest(query=query, query_type=expected_type)
            
            response = await router.retrieve(request)
            
            # When query_type is provided, it should be preserved
            assert response.query_type == expected_type
    
    @pytest.mark.asyncio
    async def test_pipeline_response_contains_citations(self, router):
        """Test pipeline response contains citation information."""
        query = "What are the Basel III capital requirements?"
        request = QueryRequest(query=query, max_results=5)
        
        response = await router.retrieve(request)
        
        # Verify sources contain content
        for source in response.sources:
            assert len(source.content) > 0
            assert source.score > 0
        
        # Response should have confidence
        assert response.confidence >= 0
        assert response.confidence <= 1


class TestE2EIntegration:
    """Integration tests for end-to-end pipeline."""
    
    @pytest.fixture
    def router(self):
        """Create a HybridRouter instance."""
        return HybridRouter()
    
    @pytest.mark.asyncio
    async def test_pipeline_with_real_world_scenario(self, router):
        """Test pipeline with a realistic financial query scenario."""
        # Scenario: Regulatory compliance officer checking Basel III requirements
        query = (
            "What are the minimum capital ratio requirements for commercial banks "
            "under Basel III framework?"
        )
        
        request = QueryRequest(
            query=query,
            query_type=QueryType.REGULATORY,
            alpha=0.7,
            max_results=10,
        )
        
        response = await router.retrieve(request)
        
        # Verify response structure
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 10  # Reasonable length answer
        assert response.query_type == QueryType.REGULATORY
        assert len(response.sources) > 0
        
        # Verify confidence is reasonable
        assert response.confidence > 0.5  # Should have good confidence for regulatory query
        
        # Verify processing completed in reasonable time
        assert response.processing_time < 5.0  # Well under 5 second target
    
    @pytest.mark.asyncio
    async def test_pipeline_with_entity_relationship_scenario(self, router):
        """Test pipeline with entity relationship scenario."""
        # Scenario: Investor researching corporate structure
        query = "What subsidiaries does Bank of America own?"
        
        request = QueryRequest(
            query=query,
            query_type=QueryType.ENTITY_RELATIONSHIP,
            alpha=0.8,  # High graph weight for entity relationships
            max_results=10,
        )
        
        response = await router.retrieve(request)
        
        # Verify response
        assert isinstance(response, HybridResponse)
        assert len(response.answer) > 0
        assert response.query_type == QueryType.ENTITY_RELATIONSHIP
        assert response.confidence > 0
        
        # Verify alpha weighting was used
        for source in response.sources:
            if hasattr(source, 'metadata'):
                assert 'fusion_weight' in source.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
