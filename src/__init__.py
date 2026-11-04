"""
Alchemist's Chimera - Hybrid Graph-Vector RAG Engine

A local hybrid RAG engine that fuses deterministic knowledge graphs 
with statistical vector search for enterprise-grade retrieval.

Built for Kiroween Hackathon 2026 with comprehensive Kiro integration.
"""

__version__ = "0.1.0"
__author__ = "Froilan Sia with Kiro AI"
__description__ = "Local hybrid graph-vector RAG engine"

from .router import HybridRouter
from .graph_store import GraphStore
from .vector_store import VectorStore
from .fusion import FusionEngine
from .intent_classifier import IntentClassifier
from .context_builder import ContextBuilder
from .response_generator import ResponseGenerator

__all__ = [
    "HybridRouter",
    "GraphStore", 
    "VectorStore",
    "FusionEngine",
    "IntentClassifier",
    "ContextBuilder",
    "ResponseGenerator",
]