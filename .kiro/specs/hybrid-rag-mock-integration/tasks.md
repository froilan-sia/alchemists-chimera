# Implementation Plan

## Overview

This document outlines the implementation tasks for fixing the mock implementation bug in the Alchemist's Chimera hybrid RAG system. The bug involves the HybridRouter component using mock retrieval methods instead of real GraphStore and VectorStore integrations. Tasks follow the exploratory bugfix workflow with property-based testing for bug condition exploration and preservation checking.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Real Component Integration Detection
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: For deterministic bugs, scope the property to the concrete failing case(s) to ensure reproducibility
  - Test that `HybridRouter._parallel_retrieval` unconditionally calls mock methods instead of real GraphStore and VectorStore components
  - Assert that when real GraphStore and VectorStore instances are available, the router still calls `_mock_graph_retrieval` and `_mock_vector_retrieval`
  - Verify that `GraphStore.retrieve()` and `VectorStore.retrieve()` methods are never called during query processing
  - Check that the router's component placeholders (`graph_store`, `vector_store`) remain `None` even when real components exist
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found to understand root cause (e.g., "HybridRouter continues to use mock methods despite real components being implemented")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Query Processing Flow
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs (non-retrieval functionality)
  - Observe intent classification logic: `HybridRouter._classify_intent` correctly identifies query types based on keywords
  - Observe alpha parameter calculation: `HybridRouter._determine_alpha` returns correct default values for each query type
  - Observe context building logic: `HybridRouter._build_context` produces proper context strings from results
  - Observe response generation: `HybridRouter._generate_response` produces mock answers based on query content
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix for Mock Implementation Bug

  - [x] 3.1 Implement dependency injection in HybridRouter constructor
    - Modify `HybridRouter.__init__` to accept `graph_store` and `vector_store` parameters
    - Add default values that instantiate real GraphStore and VectorStore using their factory functions
    - Remove placeholder `None` initialization for these components
    - Update docstring to document the new parameters
    - _Bug_Condition: isBugCondition(input) where mock methods are used unconditionally_
    - _Expected_Behavior: Proper dependency injection enabling real component usage_
    - _Preservation: Constructor should maintain backward compatibility for existing usage_
    - _Requirements: 2.3_

  - [x] 3.2 Replace mock retrieval methods with real component calls
    - Update `_parallel_retrieval` method to call `self.graph_store.retrieve()` and `self.vector_store.retrieve()`
    - Remove or refactor `_mock_graph_retrieval` and `_mock_vector_retrieval` methods
    - Add error handling for cases where components might be missing or fail
    - Update docstrings to reflect real component usage
    - _Bug_Condition: isBugCondition(input) where GraphStore.retrieve() and VectorStore.retrieve() are not called_
    - _Expected_Behavior: Real components are called for data retrieval_
    - _Preservation: Method signature and return type must remain unchanged_
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Integrate FusionEngine into router
    - Update `_fuse_results` method to use `FusionEngine` from `fusion.py`
    - Import and use `get_fusion_engine()` factory function
    - Remove duplicate fusion logic from router that exists in both router.py and fusion.py
    - Configure FusionEngine with appropriate strategy (weighted, rrf, or hybrid)
    - _Bug_Condition: isBugCondition(input) where inline fusion is used instead of FusionEngine_
    - _Expected_Behavior: FusionEngine properly fuses graph and vector results_
    - _Preservation: Fusion results should maintain same structure and ordering_
    - _Requirements: 2.1, 2.2_

  - [x] 3.4 Add proper component initialization and error handling
    - Add initialization checks in `_parallel_retrieval` to ensure components are available
    - Add meaningful error messages if components are missing or fail to initialize
    - Update health check method to report actual component status
    - Consider adding lazy initialization pattern if appropriate
    - _Bug_Condition: isBugCondition(input) where components are None without error reporting_
    - _Expected_Behavior: Proper error handling when components are unavailable_
    - _Preservation: Health check should continue to provide component status_
    - _Requirements: 2.4_

  - [x] 3.5 Add testing configuration support
    - Add `use_mocks` flag or similar configuration option to constructor
    - Keep mock methods as private helpers for testing when needed
    - Ensure production code uses real components by default
    - Document how to use mock mode for isolated testing
    - _Bug_Condition: isBugCondition(input) where mock methods are always used_
    - _Expected_Behavior: Configurable component usage based on environment_
    - _Preservation: Test environment should still support mock implementations_
    - _Requirements: 3.4_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Real Component Integration Verification
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify that `HybridRouter._parallel_retrieval` now calls real GraphStore and VectorStore components
    - Confirm that `_mock_graph_retrieval` and `_mock_vector_retrieval` are no longer used in production flow
    - Check that dependency injection works correctly
    - _Requirements: Expected Behavior Properties from design_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Query Processing Flow Verification
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - Verify intent classification logic remains unchanged
    - Verify alpha calculation logic remains unchanged
    - Verify context building logic remains unchanged
    - Verify response generation flow remains unchanged

- [x] 4. Create comprehensive tests for FusionEngine
  - Implement comprehensive tests in `tests/test_fusion.py`
  - Test weighted fusion with different alpha values (0.0, 0.5, 1.0)
  - Test Reciprocal Rank Fusion (RRF) with varying k values
  - Test deduplication functionality with duplicate content
  - Test edge cases: empty result lists, single result, all identical results
  - Test fusion statistics generation
  - Add property-based tests for fusion consistency
  - Ensure test coverage meets project standards (80%+)
  - Run tests and verify all pass
  - _Requirements: Fusion completeness from design_

- [x] 5. Create integration tests for component interactions
  - Test HybridRouter with real GraphStore and VectorStore integration
  - Test full query processing pipeline with mock data loaded into stores
  - Test error handling when components fail or return empty results
  - Test performance with real vs mock implementations
  - Test health check functionality with real components
  - Test that retrieved data is properly fused and presented
  - Add end-to-end test with sample queries and expected response patterns
  - Verify integration tests pass with the new implementation
  - _Requirements: End-to-end functionality verification_

- [x] 6. Checkpoint - Ensure all tests pass
  - Run all existing tests to ensure nothing is broken
  - Run new bug condition tests to confirm fix is working
  - Run preservation tests to confirm no regressions
  - Run fusion engine tests to verify fusion functionality
  - Run integration tests to verify component interactions
  - Check test coverage report meets project standards
  - Verify that the system can process queries with real component integration
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: Complete validation of the fix_

## Notes

- **Exploration Testing**: Task 1 MUST be completed before implementing any fix. The test should FAIL on unfixed code, confirming the bug exists.
- **Observation-First Methodology**: Task 2 requires observing behavior on UNFIXED code first before writing preservation tests.
- **Property-Based Testing**: Both exploration and preservation tests use property-based testing for stronger guarantees.
- **Dependency Order**: Tasks must be completed in sequence - exploration tests, preservation tests, then implementation.
- **Component Integration**: The fix involves proper dependency injection and integration of existing GraphStore and VectorStore components.
- **Testing Strategy**: After implementation, re-run the same tests from tasks 1 and 2 to verify the fix works and no regressions occur.
- **Fusion Engine**: Proper integration with the existing FusionEngine component is required.
- **Backward Compatibility**: The fix must maintain backward compatibility for existing usage patterns.