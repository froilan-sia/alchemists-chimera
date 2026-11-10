# Bugfix Requirements Document

## Introduction

The Alchemist's Chimera hybrid RAG system currently uses mock implementations for graph and vector stores instead of real integrations. The router.py file unconditionally executes `_mock_graph_retrieval` and `_mock_vector_retrieval` methods that return hardcoded data, preventing the system from actually retrieving real data from knowledge graphs or vector databases. This bug prevents the hybrid RAG system from functioning as designed.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the HybridRouter processes a query THEN the system executes `_mock_graph_retrieval` method instead of calling the real GraphStore component
1.2 WHEN the HybridRouter processes a query THEN the system executes `_mock_vector_retrieval` method instead of calling the real VectorStore component
1.3 WHEN the HybridRouter is initialized THEN the `graph_store` and `vector_store` components are set to `None` without proper dependency injection
1.4 WHEN the router's `_parallel_retrieval` method is called THEN it unconditionally falls back to mock methods without checking component availability

### Expected Behavior (Correct)

2.1 WHEN the HybridRouter processes a query THEN the system SHALL call the real GraphStore component's retrieval methods
2.2 WHEN the HybridRouter processes a query THEN the system SHALL call the real VectorStore component's retrieval methods
2.3 WHEN the HybridRouter is initialized THEN the `graph_store` and `vector_store` components SHALL be properly injected as required dependencies
2.4 WHEN the router's `_parallel_retrieval` method is called THEN it SHALL raise a RuntimeError if required components are not available instead of silently using mocks

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the system processes entity relationship queries THEN the system SHALL CONTINUE TO return results from graph-based retrieval
3.2 WHEN the system processes semantic queries THEN the system SHALL CONTINUE TO return results from vector-based retrieval
3.3 WHEN the system processes hybrid queries THEN the system SHALL CONTINUE TO fuse results from both graph and vector stores
3.4 WHEN the system is in a test environment with explicit mock flag THEN the system SHALL CONTINUE TO allow mock implementations for isolated testing