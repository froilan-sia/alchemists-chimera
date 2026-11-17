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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VECTOR_COLLECTION_NAME = "documents"


def canonical_vector_store_path(path: Optional[str] = None) -> str:
    """Return the absolute Chroma path shared by every application process.

    Relative paths depend on the process working directory. FastAPI and
    Streamlit can have different working directories in local and Docker
    launches, so resolving the configured path here prevents each process
    from opening a different empty Chroma database.
    """
    configured = Path(path or settings.vector_store_path).expanduser()
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    return str(configured.resolve())


class VectorStore:
    """Vector store using ChromaDB for semantic search."""

    def __init__(self, persist_directory: str = None):
        """Initialize vector store with ChromaDB."""
        self.logger = logging.getLogger(__name__)

        # Use one absolute path in FastAPI, Streamlit, and ingestion workers.
        self.persist_directory = canonical_vector_store_path(persist_directory)
        self.connection_pool = DatabaseConnectionPool(
            getattr(settings, "database_pool_size", 4)
        )

        # Initialize ChromaDB client.
        self.client = chromadb.PersistentClient(path=self.persist_directory)

        # Initialize embedding function (will be set later).
        self.embedding_function = None

        # Collection to use. Keep the name on the instance so refreshes cannot
        # accidentally switch to a second collection.
        self.collection_name = VECTOR_COLLECTION_NAME
        self.collection = None

        self.logger.info(
            "VectorStore initialized with persist_directory=%s, collection=%s",
            self.persist_directory,
            self.collection_name,
        )

    def initialize(self, collection_name: str = VECTOR_COLLECTION_NAME) -> bool:
        """Initialize the canonical Chroma collection."""
        try:
            self.collection_name = collection_name
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            self.logger.info("Collection '%s' initialized", self.collection_name)
            self.logger.info("Collection size: %s documents", self.collection.count())

            return True

        except Exception as error:
            self.logger.error("Failed to initialize vector store: %s", error)
            return False

    def _refresh_collection(self) -> None:
        """Reload the named collection so another process's writes are visible."""
        if self.collection is None:
            if not self.initialize(self.collection_name):
                raise RuntimeError("Unable to initialize the Chroma vector collection")
            return

        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception:
            # The collection may have been removed between calls. Recreate it
            # with the same canonical name rather than silently using a stale
            # empty object.
            if not self.initialize(self.collection_name):
                raise RuntimeError("Unable to refresh the Chroma vector collection")

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
            else:
                self._refresh_collection()

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
    
    def upsert_documents(
        self,
        documents: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Insert or replace documents using caller-provided stable IDs."""
        if self.collection is None:
            self.initialize()
        else:
            self._refresh_collection()
        document_ids = ids or [f"doc_{i}" for i in range(len(documents))]
        if len(document_ids) != len(documents):
            raise ValueError("ids and documents must have the same length")
        with self.connection_pool.connection():
            self.collection.upsert(
                documents=documents,
                metadatas=metadata or [{} for _ in documents],
                ids=document_ids,
            )
        return document_ids

    def has_source_hash(self, source_hash: str) -> bool:
        """Return whether Chroma contains at least one chunk for a source."""
        if self.collection is None:
            self.initialize()
        else:
            self._refresh_collection()
        try:
            result = self.collection.get(
                where={"source_sha256": source_hash}, include=["metadatas"]
            )
        except (TypeError, ValueError):
            return False
        return bool(result and result.get("ids"))

    def retrieve(self, query: str, n_results: int = 10) -> List[RetrievalResult]:
        """Retrieve similar documents for a query."""
        try:
            if self.collection is None:
                self.initialize()
            else:
                # FastAPI ingestion and Streamlit retrieval run in separate
                # processes. Re-acquire the collection so writes committed by
                # the bootstrap worker are visible to this router.
                self._refresh_collection()

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
            else:
                self._refresh_collection()

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
            else:
                self._refresh_collection()

            return {
                "name": self.collection.name,
                "count": self.collection.count(),
                "metadata": self.collection.metadata
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def health_check(self) -> Dict[str, str]:
        """Check health of vector store."""
        try:
            if self.collection is None:
                self.initialize()
            else:
                self._refresh_collection()

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
