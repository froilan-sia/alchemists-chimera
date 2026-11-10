"""
Tests for the FusionEngine component.

Demonstrates comprehensive testing of hybrid result fusion.
"""

import pytest
from unittest.mock import Mock

from src.config import QueryType
from src.models import RetrievalResult, RetrievalSource
from src.fusion import FusionEngine, FusionConfig


class TestFusionEngine:
    """Test suite for FusionEngine."""
    
    @pytest.fixture
    def fusion_engine(self):
        """Create a FusionEngine instance for testing."""
        return FusionEngine()
    
    @pytest.fixture
    def graph_results(self):
        """Create sample graph results."""
        return [
            RetrievalResult(
                content="Graph result 1: Entity relationships in financial sector",
                source=RetrievalSource.GRAPH,
                score=0.85,
                metadata={"type": "entity", "query": "subsidiaries"},
                entity_links=["http://example.org/finance#Bank1"],
            ),
            RetrievalResult(
                content="Graph result 2: Regulatory framework information",
                source=RetrievalSource.GRAPH,
                score=0.72,
                metadata={"type": "regulation", "query": "basel"},
            ),
        ]
    
    @pytest.fixture
    def vector_results(self):
        """Create sample vector results."""
        return [
            RetrievalResult(
                content="Vector result 1: Semantic information about banking",
                source=RetrievalSource.VECTOR,
                score=0.78,
                metadata={"type": "document", "chunk": 1},
            ),
            RetrievalResult(
                content="Vector result 2: Contextual data on financial markets",
                source=RetrievalSource.VECTOR,
                score=0.65,
                metadata={"type": "document", "chunk": 2},
            ),
        ]
    
    def test_initialization(self, fusion_engine):
        """Test that fusion engine initializes correctly."""
        assert fusion_engine is not None
        assert fusion_engine.config is not None
        assert fusion_engine.config.strategy == "weighted"
        assert fusion_engine.config.default_alpha == 0.5
    
    def test_weighted_fusion_high_alpha(self, fusion_engine, graph_results, vector_results):
        """Test weighted fusion with high alpha (graph-weighted)."""
        alpha = 0.8  # Heavy weight on graph results
        
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha)
        
        assert len(fused_results) > 0
        assert len(fused_results) <= fusion_engine.config.max_results
        
        # Check that all results are marked as HYBRID
        for result in fused_results:
            assert result.source == RetrievalSource.HYBRID
        
        # With high alpha, graph results should have higher scores
        graph_scores = [r.score for r in fused_results if "graph" in r.metadata.get("original_source", "")]
        vector_scores = [r.score for r in fused_results if "vector" in r.metadata.get("original_source", "")]
        
        if graph_scores and vector_scores:
            # Graph scores should be higher with alpha=0.8
            avg_graph_score = sum(graph_scores) / len(graph_scores)
            avg_vector_score = sum(vector_scores) / len(vector_scores)
            assert avg_graph_score > avg_vector_score
    
    def test_weighted_fusion_low_alpha(self, fusion_engine, graph_results, vector_results):
        """Test weighted fusion with low alpha (vector-weighted)."""
        alpha = 0.2  # Heavy weight on vector results
        
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha)
        
        assert len(fused_results) > 0
        
        # With low alpha, vector results should have higher scores
        graph_scores = [r.score for r in fused_results if "graph" in r.metadata.get("original_source", "")]
        vector_scores = [r.score for r in fused_results if "vector" in r.metadata.get("original_source", "")]
        
        if graph_scores and vector_scores:
            # Vector scores should be higher with alpha=0.2
            avg_graph_score = sum(graph_scores) / len(graph_scores)
            avg_vector_score = sum(vector_scores) / len(vector_scores)
            assert avg_vector_score > avg_graph_score
    
    def test_weighted_fusion_balanced_alpha(self, fusion_engine, graph_results, vector_results):
        """Test weighted fusion with balanced alpha."""
        alpha = 0.5  # Equal weight
        
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha)
        
        assert len(fused_results) > 0
        
        # Check fusion metadata
        for result in fused_results:
            assert "fusion_weight" in result.metadata
            assert "original_source" in result.metadata
            assert "original_score" in result.metadata
    
    def test_rrf_fusion(self, fusion_engine, graph_results, vector_results):
        """Test Reciprocal Rank Fusion (RRF)."""
        # Configure for RRF
        config = FusionConfig(strategy="rrf", rrf_k=60)
        rrf_engine = FusionEngine(config)
        
        fused_results = rrf_engine.fuse(graph_results, vector_results)
        
        assert len(fused_results) > 0
        
        # Check RRF metadata
        for result in fused_results:
            assert result.metadata.get("fusion_method") == "rrf"
            assert "original_source" in result.metadata
    
    def test_hybrid_fusion_strategy(self, fusion_engine, graph_results, vector_results):
        """Test hybrid fusion strategy."""
        # Configure for hybrid
        config = FusionConfig(strategy="hybrid")
        hybrid_engine = FusionEngine(config)
        
        fused_results = hybrid_engine.fuse(graph_results, vector_results, alpha=0.6)
        
        assert len(fused_results) > 0
    
    def test_deduplication(self, fusion_engine):
        """Test deduplication functionality."""
        # Create duplicate results
        duplicate_content = "This is duplicate content"
        
        graph_results = [
            RetrievalResult(
                content=duplicate_content,
                source=RetrievalSource.GRAPH,
                score=0.8,
                metadata={"source": "graph"},
            ),
        ]
        
        vector_results = [
            RetrievalResult(
                content=duplicate_content,
                source=RetrievalSource.VECTOR,
                score=0.7,
                metadata={"source": "vector"},
            ),
            RetrievalResult(
                content="Unique content",
                source=RetrievalSource.VECTOR,
                score=0.6,
                metadata={"source": "vector"},
            ),
        ]
        
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha=0.5)
        
        # Should have 2 results (1 duplicate removed)
        assert len(fused_results) == 2
        
        # Check that duplicate is removed
        contents = [r.content.strip().lower() for r in fused_results]
        assert duplicate_content.lower() in contents
        assert "unique content" in contents
    
    def test_empty_results(self, fusion_engine):
        """Test fusion with empty result lists."""
        # Empty graph results
        fused1 = fusion_engine.fuse([], [], alpha=0.5)
        assert len(fused1) == 0
        
        # Only graph results
        graph_results = [
            RetrievalResult(
                content="Graph only",
                source=RetrievalSource.GRAPH,
                score=0.8,
                metadata={},
            ),
        ]
        fused2 = fusion_engine.fuse(graph_results, [], alpha=0.5)
        assert len(fused2) == 1
        assert fused2[0].content == "Graph only"
        
        # Only vector results
        vector_results = [
            RetrievalResult(
                content="Vector only",
                source=RetrievalSource.VECTOR,
                score=0.7,
                metadata={},
            ),
        ]
        fused3 = fusion_engine.fuse([], vector_results, alpha=0.5)
        assert len(fused3) == 1
        assert fused3[0].content == "Vector only"
    
    def test_max_results_limit(self, fusion_engine):
        """Test that fusion respects max_results limit."""
        # Create many results
        graph_results = [
            RetrievalResult(
                content=f"Graph result {i}",
                source=RetrievalSource.GRAPH,
                score=max(0.2, 0.9 - (i * 0.05)),
                metadata={},
            ) for i in range(10)
        ]
        
        vector_results = [
            RetrievalResult(
                content=f"Vector result {i}",
                source=RetrievalSource.VECTOR,
                score=max(0.1, 0.8 - (i * 0.05)),
                metadata={},
            ) for i in range(10)
        ]
        
        # Default config has max_results=10
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha=0.5)
        
        assert len(fused_results) <= 10
        
        # Test with custom config
        config = FusionConfig(max_results=5)
        limited_engine = FusionEngine(config)
        limited_results = limited_engine.fuse(graph_results, vector_results, alpha=0.5)
        
        assert len(limited_results) <= 5
    
    def test_fusion_statistics(self, fusion_engine, graph_results, vector_results):
        """Test fusion statistics generation."""
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha=0.6)
        
        stats = fusion_engine.get_fusion_statistics(
            graph_results, vector_results, fused_results
        )
        
        assert "graph_results_count" in stats
        assert "vector_results_count" in stats
        assert "fused_results_count" in stats
        assert "fusion_strategy" in stats
        assert "alpha" in stats
        
        assert stats["graph_results_count"] == len(graph_results)
        assert stats["vector_results_count"] == len(vector_results)
        assert stats["fused_results_count"] == len(fused_results)
        assert stats["fusion_strategy"] == "weighted"
        assert stats["alpha"] == 0.5  # Default alpha from config
    
    def test_cross_encoder_rerank(self, fusion_engine, graph_results, vector_results):
        """Test cross-encoder reranking (placeholder)."""
        fused_results = fusion_engine.fuse(graph_results, vector_results, alpha=0.5)
        
        # Test reranking (currently a no-op)
        reranked = fusion_engine.cross_encoder_rerank(fused_results, "test query")
        
        assert len(reranked) == len(fused_results)
        # In current implementation, reranking doesn't change order
        # This test verifies the interface works


class TestFusionConfig:
    """Tests for FusionConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = FusionConfig()
        
        assert config.strategy == "weighted"
        assert config.default_alpha == 0.5
        assert config.rrf_k == 60
        assert config.max_results == 10
        assert config.deduplicate == True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = FusionConfig(
            strategy="rrf",
            default_alpha=0.7,
            rrf_k=100,
            max_results=20,
            deduplicate=False,
        )
        
        assert config.strategy == "rrf"
        assert config.default_alpha == 0.7
        assert config.rrf_k == 100
        assert config.max_results == 20
        assert config.deduplicate == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
