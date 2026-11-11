"""
Vector Store Engine for Alchemist's Chimera Hybrid RAG Engine

Provides ChromaDB-based vector search capabilities for semantic retrieval.
"""

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

import chromadb
from chromadb.config import Settings

from .config import settings
from .models import RetrievalResult, RetrievalSource
from .performance import DatabaseConnectionPool

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store using ChromaDB for semantic search."""
    
    def __init__(self, persist_directory: str = None):
        """Initialize vector store with ChromaDB."""
        self.logger = logging.getLogger(__name__)
        
        # Use provided path or default from settings
        self.persist_directory = persist_directory or settings.vector_store_path
        self.connection_pool = DatabaseConnectionPool(
            getattr(settings, "database_pool_size", 4)
        )
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # Initialize embedding function (will be set later)
        self.embedding_function = None
        
        # Collection to use
        self.collection = None
        
        self.logger.info(f"VectorStore initialized with persist_directory={self.persist_directory}")
    
    def initialize(self, collection_name: str = "documents"):
        """Initialize vector store with collection."""
        try:
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            self.logger.info(f"Collection '{collection_name}' initialized")
            self.logger.info(f"Collection size: {self.collection.count()} documents")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize vector store: {e}")
            return False
    
    def add_documents(
        self,
        documents: List[str],
        metadata: List[Dict[str, Any]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Add documents using pooled persistence and optional stable IDs."""
        try:
            if self.collection is None:
                self.initialize()

            document_ids = ids or [f"doc_{i}" for i in range(len(documents))]
            if len(document_ids) != len(documents):
                raise ValueError("ids and documents must have the same length")

            with self.connection_pool.connection():
                self.collection.add(
                    documents=documents,
                    metadatas=metadata or [{} for _ in documents],
                    ids=document_ids,
                )

            self.logger.info("Added %s documents to vector store", len(documents))
            return document_ids

        except Exception as e:
            self.logger.error(f"Error adding documents: {e}")
            return []
    
    def retrieve(self, query: str, n_results: int = 10) -> List[RetrievalResult]:
        """Retrieve similar documents for a query."""
        try:
            if self.collection is None:
                self.initialize()
            
            # Query collection through the bounded persistent-store pool.
            with self.connection_pool.connection():
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results
                )
            
            # Process results
            retrieval_results = []
            
            if results and results.get('documents'):
                documents = results['documents'][0]
                distances = results.get('distances', [[1.0] * len(documents)])[0]
                
                for i, (doc, distance) in enumerate(zip(documents, distances)):
                    # Convert distance to score (cosine distance -> similarity score)
                    score = 1.0 - min(distance, 1.0)
                    
                    # Create retrieval result
                    result = RetrievalResult(
                        content=doc,
                        source=RetrievalSource.VECTOR,
                        score=score,
                        metadata=results.get('metadatas', [{}])[0][i] if results.get('metadatas') else {}
                    )
                    
                    retrieval_results.append(result)
            
            self.logger.info(f"Retrieved {len(retrieval_results)} results from vector store")
            
            return retrieval_results
            
        except Exception as e:
            self.logger.error(f"Error retrieving documents: {e}")
            return []
    
    def retrieve_by_metadata(self, filter: Dict[str, Any], n_results: int = 10) -> List[RetrievalResult]:
        """Retrieve documents filtered by metadata."""
        try:
            if self.collection is None:
                self.initialize()
            
            # Query with filter through the bounded persistent-store pool.
            with self.connection_pool.connection():
                results = self.collection.query(
                    query_texts=[" "],  # Empty query for metadata-only search
                    n_results=n_results,
                    where=filter
                )
            
            # Process results
            retrieval_results = []
            
            if results and results.get('documents'):
                documents = results['documents'][0]
                
                for i, doc in enumerate(documents):
                    # Default score for metadata-only search
                    score = 0.5
                    
                    result = RetrievalResult(
                        content=doc,
                        source=RetrievalSource.VECTOR,
                        score=score,
                        metadata=results.get('metadatas', [{}])[0][i] if results.get('metadatas') else {}
                    )
                    
                    retrieval_results.append(result)
            
            return retrieval_results
            
        except Exception as e:
            self.logger.error(f"Error retrieving by metadata: {e}")
            return []
    
    def hybrid_search(self, query: str, metadata_filter: Dict[str, Any] = None, n_results: int = 10) -> List[RetrievalResult]:
        """Perform hybrid search combining vector and metadata search."""
        try:
            # First do vector search
            vector_results = self.retrieve(query, n_results)
            
            # If filter provided, also do metadata search
            if metadata_filter:
                metadata_results = self.retrieve_by_metadata(metadata_filter, n_results)
                
                # Combine results (simplified - in production, use proper fusion)
                combined = vector_results + metadata_results
                
                # Remove duplicates based on content
                seen = set()
                unique_results = []
                
                for result in combined:
                    if result.content not in seen:
                        seen.add(result.content)
                        unique_results.append(result)
                
                return unique_results[:n_results]
            
            return vector_results
            
        except Exception as e:
            self.logger.error(f"Error in hybrid search: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        try:
            if self.collection is None:
                self.initialize()
            
            return {
                "name": self.collection.name,
                "count": self.collection.count,
                "metadata": self.collection.metadata
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def health_check(self) -> Dict[str, str]:
        """Check health of vector store."""
        try:
            if self.collection is None:
                self.initialize()
            
            return {
                "status": "healthy",
                "collection": self.collection.name,
                "document_count": str(self.collection.count()),
                "persist_directory": self.persist_directory,
                "connection_pool": self.connection_pool.status(),
            }
            
        except Exception as e:
            return {
                "status": f"error: {str(e)}",
                "collection": "unknown",
                "document_count": "0"
            }


# Singleton instance
vector_store_instance = None


def get_vector_store() -> VectorStore:
    """Get singleton vector store instance."""
    global vector_store_instance
    
    if vector_store_instance is None:
        vector_store_instance = VectorStore()
        vector_store_instance.initialize()
    
    return vector_store_instance
