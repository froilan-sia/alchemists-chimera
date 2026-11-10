# Hybrid RAG Mock Integration Bugfix Design

## Overview

The Alchemist's Chimera hybrid RAG system currently has mock implementations in the router component that prevent real data retrieval from knowledge graphs and vector databases. The `HybridRouter` class uses `_mock_graph_retrieval` and `_mock_vector_retrieval` methods that return hardcoded data instead of calling the real `GraphStore` and `VectorStore` components. This design document formalizes the bug condition and outlines the implementation plan to replace mock implementations with real integrations while preserving existing behavior.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when the HybridRouter uses mock retrieval methods instead of real components
- **Property (P)**: The desired behavior when processing queries - proper integration with GraphStore and VectorStore components
- **Preservation**: Existing query processing flow, intent classification, and response generation that must remain unchanged by the fix
- **HybridRouter**: The main orchestrator class in `router.py` that coordinates the hybrid retrieval pipeline
- **GraphStore**: The real graph store component in `graph_store.py` that provides RDFLib/SPARQL functionality
- **VectorStore**: The real vector store component in `vector_store.py` that provides ChromaDB functionality
- **FusionEngine**: The fusion component in `fusion.py` that properly fuses graph and vector results

## Bug Details

### Bug Condition

The bug manifests when a user submits a query through the HybridRouter. The router's `_parallel_retrieval` method unconditionally calls `_mock_graph_retrieval` and `_mock_vector_retrieval` methods that return hardcoded sample data, preventing actual data retrieval from the knowledge graph or vector database. This happens regardless of whether the real GraphStore and VectorStore components are available and functional.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type QueryRequest
  OUTPUT: boolean
  
  router := HybridRouter()
  RETURN router._parallel_retrieval(input) calls mock methods
         AND NOT router.graph_store.retrieve() is called
         AND NOT router.vector_store.retrieve() is called
END FUNCTION
```

### Examples

1. **Example: Entity Relationship Query**
   - **Input**: QueryRequest(query="What subsidiaries does Bank of America own?")
   - **Expected**: Real graph store retrieves entity relationships from ontology
   - **Actual**: Mock method returns hardcoded "Sample graph retrieval result 1"

2. **Example: Semantic Query**
   - **Input**: QueryRequest(query="Explain quantitative easing")
   - **Expected**: Real vector store performs semantic similarity search on embeddings
   - **Actual**: Mock method returns hardcoded "Sample vector retrieval result 1"

3. **Example: Hybrid Query**
   - **Input**: QueryRequest(query="Basel III capital requirements for banks")
   - **Expected**: Both graph and vector stores retrieve relevant information
   - **Actual**: Both mock methods return hardcoded sample data

4. **Edge Case: Empty Query**
   - **Input**: QueryRequest(query="")
   - **Expected**: Proper error handling or empty results from real components
   - **Actual**: Mock methods still return hardcoded data even for empty queries

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Query intent classification logic must continue to work exactly as before
- Alpha parameter determination based on query type must remain unchanged
- Response generation flow and confidence scoring must continue to work
- Health check functionality must remain intact
- Existing API interfaces (if any) must not be broken

**Scope:**
All aspects of the system that do NOT involve the replacement of mock retrieval methods should be completely unaffected by this fix. This includes:
- Query preprocessing and intent classification
- Alpha parameter calculation
- Context building and response generation
- Error handling patterns
- Logging and monitoring

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Incomplete Integration**: The GraphStore and VectorStore components were implemented but never properly integrated into the HybridRouter
   - GraphStore exists in `graph_store.py` with full SPARQL/ontology functionality
   - VectorStore exists in `vector_store.py` with ChromaDB integration
   - HybridRouter was left with placeholder implementations for rapid prototyping

2. **Dependency Injection Missing**: The HybridRouter constructor initializes component placeholders to `None` without proper dependency injection
   - Components are set to `None` in `__init__`
   - No mechanism to inject real implementations
   - Mock methods are the default fallback

3. **Lazy Loading Pattern**: The code uses a lazy loading pattern but never actually loads the real components
   - Comment mentions "components will be lazy-loaded"
   - But lazy loading logic is missing or incomplete
   - Mock methods are called unconditionally

4. **Testing Focus**: Development may have focused on building individual components separately without integrating them
   - Components developed in isolation
   - Integration layer left with mocks
   - End-to-end testing not implemented

## Correctness Properties

Property 1: Bug Condition - Real Component Integration

_For any_ QueryRequest input where the bug condition holds (mock methods are being used), the fixed HybridRouter SHALL call the real GraphStore.retrieve() and VectorStore.retrieve() methods instead of mock methods, enabling actual data retrieval from knowledge graphs and vector databases.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Existing Query Processing Flow

_For any_ aspect of the system not directly related to mock method replacement (intent classification, alpha calculation, context building, response generation), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality and interfaces.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/router.py`

**Class**: `HybridRouter`

**Specific Changes**:
1. **Dependency Injection**: Modify `__init__` to accept GraphStore and VectorStore dependencies
   - Add `graph_store` and `vector_store` parameters with default values
   - Remove placeholder `None` initialization
   - Update lazy loading comment or implement actual lazy loading

2. **Mock Method Replacement**: Replace `_mock_graph_retrieval` and `_mock_vector_retrieval` with calls to real components
   - Update `_parallel_retrieval` to call `self.graph_store.retrieve()` and `self.vector_store.retrieve()`
   - Remove mock methods entirely or keep them for testing with explicit flags
   - Add error handling for missing components

3. **Fusion Engine Integration**: Replace inline fusion logic with proper FusionEngine usage
   - Update `_fuse_results` to use the FusionEngine from `fusion.py`
   - Remove duplicate fusion logic from router
   - Import and use `get_fusion_engine()` factory function

4. **Component Initialization**: Ensure components are properly initialized
   - Add initialization checks in `_parallel_retrieval`
   - Raise meaningful errors if components are not available
   - Consider lazy initialization pattern if needed

5. **Testing Support**: Add configuration option for mock mode (for testing)
   - Add `use_mocks` flag to constructor
   - Keep mock methods as private helpers for testing
   - Ensure production code uses real components by default

**File**: `tests/test_fusion.py`

**Specific Changes**:
1. **Create Test File**: Implement comprehensive tests for FusionEngine
   - Test weighted fusion with different alpha values
   - Test Reciprocal Rank Fusion (RRF)
   - Test deduplication functionality
   - Test edge cases and error conditions

2. **Integration Tests**: Add tests for router-component integration
   - Test HybridRouter with real GraphStore and VectorStore
   - Test fusion integration through router
   - Test error handling when components are unavailable

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that instantiate HybridRouter and verify that mock methods are called instead of real component methods. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Mock Method Detection Test**: Instantiate HybridRouter and assert that `_parallel_retrieval` calls mock methods (will fail on unfixed code)
2. **Component Integration Test**: Inject real GraphStore/VectorStore and assert they are not called (will fail on unfixed code)
3. **Fusion Engine Test**: Verify inline fusion is used instead of FusionEngine (will fail on unfixed code)
4. **Error Handling Test**: Test behavior when components are None (may fail on unfixed code)

**Expected Counterexamples**:
- Mock methods are called even when real components are available
- GraphStore.retrieve() and VectorStore.retrieve() are never called
- FusionEngine is not utilized
- No error is raised when components are missing

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  router := HybridRouter(graph_store=real_graph_store, vector_store=real_vector_store)
  result := router.retrieve(input)
  ASSERT result.sources contains real data from components
  ASSERT NOT result.sources contains mock data
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  original_router := OriginalHybridRouter()
  fixed_router := FixedHybridRouter(graph_store=real_graph_store, vector_store=real_vector_store)
  
  // For non-retrieval aspects, behavior should be identical
  ASSERT original_router._classify_intent(input) = fixed_router._classify_intent(input)
  ASSERT original_router._determine_alpha(input) = fixed_router._determine_alpha(input)
  ASSERT original_router._build_context(mock_results, input) = fixed_router._build_context(mock_results, input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for intent classification, alpha calculation, and context building, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Intent Classification Preservation**: Verify query type classification works identically before and after fix
2. **Alpha Calculation Preservation**: Verify alpha parameter calculation remains unchanged
3. **Context Building Preservation**: Verify context building logic produces identical output for identical inputs
4. **Response Generation Preservation**: Verify response generation produces similar outputs for similar inputs

### Unit Tests

- Test dependency injection in HybridRouter constructor
- Test `_parallel_retrieval` calls real components when available
- Test error handling when components are missing
- Test FusionEngine integration in `_fuse_results`
- Test mock mode configuration for testing

### Property-Based Tests

- Generate random query strings and verify intent classification consistency
- Generate random alpha values and verify fusion calculations
- Generate random result sets and verify context building
- Test that all non-retrieval functionality remains identical across many scenarios

### Integration Tests

- Test full pipeline with real GraphStore and VectorStore
- Test component initialization and health checks
- Test error recovery when components fail
- Test performance of real integrations vs mock implementations
- Verify that retrieved data is properly fused and presented