"""
Fusion Engine for Alchemist's Chimera Hybrid RAG Engine

Combines and ranks results from graph and vector retrieval engines
using weighted scoring and Reciprocal Rank Fusion (RRF).
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import RetrievalResult, RetrievalSource

logger = logging.getLogger(__name__)


@dataclass
class FusionConfig:
    """Configuration for fusion algorithm."""
    
    strategy: str = "weighted"
    default_alpha: float = 0.5
    rrf_k: int = 60  # RRF constant
    max_results: int = 10
    deduplicate: bool = True


class FusionEngine:
    """Engine for fusing graph and vector retrieval results."""
    
    def __init__(self, config: FusionConfig = None):
        """Initialize fusion engine with configuration."""
        self.config = config or FusionConfig()
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"FusionEngine initialized with strategy={self.config.strategy}")
    
    def fuse(
        self,
        graph_results: List[RetrievalResult],
        vector_results: List[RetrievalResult],
        alpha: float = None,
        query_type: Any = None,
        max_results: int = None,
    ) -> List[RetrievalResult]:
        """Fuse graph and vector retrieval results using configured strategy.

        Entity-relationship queries retain the best vector chunk even when the
        graph receives the 80% routing weight.
        """
        try:
            alpha = alpha if alpha is not None else self.config.default_alpha
            limit = max_results or self.config.max_results
            relationship_query = getattr(query_type, "value", query_type) == "entity_relationship"
            self.logger.info("Fusing results with alpha=%s", alpha)
            
            # Apply selected strategy
            if self.config.strategy == "weighted":
                fused_results = self._weighted_fusion(
                    graph_results, vector_results, alpha
                )
            elif self.config.strategy == "rrf":
                fused_results = self._reciprocal_rank_fusion(
                    graph_results, vector_results
                )
            elif self.config.strategy == "hybrid":
                # Keep the dynamic alpha. The old implementation computed
                # weighted results and then discarded them before returning RRF.
                fused_results = self._weighted_fusion(
                    graph_results, vector_results, alpha
                )
            else:
                # Default to weighted
                fused_results = self._weighted_fusion(
                    graph_results, vector_results, alpha
                )
            
            if self.config.deduplicate:
                fused_results = self._deduplicate(fused_results)
            fused_results.sort(key=lambda result: result.score, reverse=True)
            fused_results = fused_results[:limit]

            if relationship_query and graph_results and vector_results and limit > 1:
                fused_results = self._ensure_vector_result(
                    fused_results, vector_results, limit, alpha
                )

            self.logger.info("Fusion produced %s results", len(fused_results))
            return fused_results
            
        except Exception as e:
            self.logger.error(f"Error in fusion: {e}")
            return []
    
    def _weighted_fusion(
        self,
        graph_results: List[RetrievalResult],
        vector_results: List[RetrievalResult],
        alpha: float
    ) -> List[RetrievalResult]:
        """Apply weighted fusion: α * graph_score + (1-α) * vector_score."""
        self.logger.debug(f"Weighted fusion: α={alpha}")
        
        fused = []
        
        # Process graph results with alpha weight
        for result in graph_results:
            fused_score = result.score * alpha
            fused.append(
                RetrievalResult(
                    content=result.content,
                    source=RetrievalSource.HYBRID,
                    score=fused_score,
                    metadata={
                        **result.metadata,
                        "fusion_weight": alpha,
                        "original_source": "graph",
                        "original_score": result.score
                    },
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
                    metadata={
                        **result.metadata,
                        "fusion_weight": 1 - alpha,
                        "original_source": "vector",
                        "original_score": result.score
                    },
                    entity_links=result.entity_links,
                )
            )
        
        # Sort by fused score
        fused.sort(key=lambda x: x.score, reverse=True)
        
        return fused
    
    def _reciprocal_rank_fusion(
        self,
        graph_results: List[RetrievalResult],
        vector_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """Apply Reciprocal Rank Fusion (RRF)."""
        self.logger.debug("RRF fusion")
        
        # Create combined ranked lists
        combined = {}
        
        # Add graph results
        for i, result in enumerate(graph_results):
            rank = i + 1  # 1-indexed
            score = 1.0 / (self.config.rrf_k + rank)
            
            content_hash = hash(result.content)
            
            if content_hash in combined:
                combined[content_hash].score += score
            else:
                combined[content_hash] = RetrievalResult(
                    content=result.content,
                    source=RetrievalSource.HYBRID,
                    score=score,
                    metadata={
                        **result.metadata,
                        "fusion_method": "rrf",
                        "original_source": "graph"
                    },
                    entity_links=result.entity_links,
                )
        
        # Add vector results
        for i, result in enumerate(vector_results):
            rank = i + 1  # 1-indexed
            score = 1.0 / (self.config.rrf_k + rank)
            
            content_hash = hash(result.content)
            
            if content_hash in combined:
                combined[content_hash].score += score
            else:
                combined[content_hash] = RetrievalResult(
                    content=result.content,
                    source=RetrievalSource.HYBRID,
                    score=score,
                    metadata={
                        **result.metadata,
                        "fusion_method": "rrf",
                        "original_source": "vector"
                    },
                    entity_links=result.entity_links,
                )
        
        # Convert to list and sort
        fused = list(combined.values())
        fused.sort(key=lambda x: x.score, reverse=True)
        
        return fused
    
    def _ensure_vector_result(
        self,
        fused_results: List[RetrievalResult],
        vector_results: List[RetrievalResult],
        limit: int,
        alpha: float,
    ) -> List[RetrievalResult]:
        """Keep one vector result visible when relationship fusion has both branches."""
        if any(result.metadata.get("original_source") == "vector" for result in fused_results):
            return fused_results

        best_vector = max(vector_results, key=lambda result: result.score)
        vector_result = RetrievalResult(
            content=best_vector.content,
            source=RetrievalSource.HYBRID,
            score=best_vector.score * (1 - alpha),
            metadata={
                **best_vector.metadata,
                "fusion_weight": 1 - alpha,
                "original_source": "vector",
                "original_score": best_vector.score,
            },
            entity_links=best_vector.entity_links,
            document_id=best_vector.document_id,
            chunk_index=best_vector.chunk_index,
        )
        if len(fused_results) >= limit:
            fused_results = fused_results[: max(0, limit - 1)]
        fused_results.append(vector_result)
        fused_results.sort(key=lambda result: result.score, reverse=True)
        return fused_results

    def _deduplicate(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """Remove duplicate results based on content."""
        seen = set()
        unique = []
        
        for result in results:
            # Use content as deduplication key
            content_key = result.content.strip().lower()
            
            if content_key not in seen:
                seen.add(content_key)
                unique.append(result)
        
        if len(unique) < len(results):
            self.logger.info(
                f"Deduplication removed {len(results) - len(unique)} duplicates"
            )
        
        return unique
    
    def cross_encoder_rerank(
        self,
        results: List[RetrievalResult],
        query: str
    ) -> List[RetrievalResult]:
        """Optionally rerank results using cross-encoder (for future enhancement)."""
        # This would use a cross-encoder model to refine rankings
        # For now, return results as-is
        return results
    
    def get_fusion_statistics(
        self,
        graph_results: List[RetrievalResult],
        vector_results: List[RetrievalResult],
        fused_results: List[RetrievalResult]
    ) -> Dict[str, Any]:
        """Get statistics about the fusion process."""
        return {
            "graph_results_count": len(graph_results),
            "vector_results_count": len(vector_results),
            "fused_results_count": len(fused_results),
            "deduplication_rate": (
                (len(graph_results) + len(vector_results) - len(fused_results)) /
                (len(graph_results) + len(vector_results)) if graph_results or vector_results else 0
            ),
            "fusion_strategy": self.config.strategy,
            "alpha": self.config.default_alpha,
        }


# Singleton instance
fusion_engine_instance = None


def get_fusion_engine(config: FusionConfig = None) -> FusionEngine:
    """Get singleton fusion engine instance."""
    global fusion_engine_instance
    
    if fusion_engine_instance is None:
        fusion_engine_instance = FusionEngine(config)
    
    return fusion_engine_instance
