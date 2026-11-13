# Staging Adapter Approval Flag Bugfix Design

## Overview

The Surgeon’s Table ingestion path cannot construct the compatibility staging adapter with the `require_human_approval` keyword. The adapter currently exposes only `staging_path`, while the comprehensive backend already supports the approval flag. In addition, the adapter module replaces its imported `StagingManager` name with `CompatibleStagingManager` at module scope, so the adapter’s backend construction must use a stable reference to the comprehensive class.

The minimal safe fix is to preserve the existing first positional argument, add `require_human_approval: bool = True` to `CompatibleStagingManager.__init__`, and pass the exact value to the comprehensive backend through a private or explicitly aliased backend class reference. Existing callers with no flag or only a staging path continue to work and retain the adapter’s human-approval default. No changes to the Surgeon’s Table rendering behavior or to the underlying approval workflow are required.

## Glossary

- **Bug_Condition (C)**: A call that constructs `CompatibleStagingManager` or its public alias with `require_human_approval=True` or `False` and receives a constructor error instead of an adapter instance.
- **Property (P)**: The required behavior for a buggy construction: the adapter initializes successfully and its comprehensive backend has the exact requested approval flag.
- **Preservation**: Existing construction forms, adapter delegation methods, and approval-mode behavior remain unchanged for callers outside the constructor incompatibility.
- **CompatibleStagingManager**: The backward-compatibility adapter in `src/ingestor/staging_adapter.py`.
- **Comprehensive backend**: The `StagingManager` implementation in `src/staging_manager.py`, whose `require_human_approval` flag controls whether valid triples remain pending or may be auto-approved.
- **Public staging alias**: The module-level `StagingManager = CompatibleStagingManager` assignment in `src/ingestor/staging_adapter.py`, retained for existing imports.
- **Surgeon’s Table extraction path**: The Streamlit path in `components/surgeons_table.py` that obtains a pipeline from `app.py`, processes an uploaded PDF, and uses the pipeline’s staging manager.

## Bug Details

### Bug Condition

The bug manifests when the staging adapter is constructed with the approval-policy keyword. `CompatibleStagingManager.__init__` accepts only `staging_path`, so a caller that supplies `require_human_approval` raises `TypeError` before the extraction pipeline can start. The module-level public alias also shadows the imported comprehensive `StagingManager`; after the module loads, an unqualified `StagingManager(...)` inside the adapter resolves back to the adapter class rather than the comprehensive backend.

**Formal Specification:**

```text
FUNCTION isBugCondition(input)
  INPUT: input containing constructor, staging_path, and optional require_human_approval
  OUTPUT: boolean

  is_adapter_constructor := input.constructor IS CompatibleStagingManager
                          OR input.constructor IS public staging_adapter.StagingManager
  has_explicit_flag := input.require_human_approval IS True
                    OR input.require_human_approval IS False
  adapter_rejects_or_cannot_forward := constructor_raises_unexpected_keyword(input)
                                    OR backend_does_not_receive_exact_flag(input)

  RETURN is_adapter_constructor
         AND has_explicit_flag
         AND adapter_rejects_or_cannot_forward
END FUNCTION
```

### Examples

- `CompatibleStagingManager(tmp_path, require_human_approval=True)` currently raises `TypeError: __init__() got an unexpected keyword argument 'require_human_approval'`. After the fix it must construct an adapter whose comprehensive backend has `require_human_approval is True`.
- `staging_adapter.StagingManager(tmp_path, require_human_approval=False)` uses the public compatibility alias. After the fix it must construct successfully and set the backend flag to `False`, enabling the comprehensive manager’s existing valid-triple auto-approval behavior.
- `CompatibleStagingManager(tmp_path)` is an existing caller form. After the fix it must still construct and must use the adapter default `require_human_approval=True`, keeping valid candidates pending until review.
- In the Surgeon’s Table flow, pressing “Start extraction” causes `pipeline_factory` to create `IngestionPipeline`, which calls `get_staging_manager(Path(...), use_comprehensive=True)`. The current adapter construction can fail before `process_pdf()` runs when the approval keyword is used. After the fix, pipeline initialization and the extraction-to-staging path must proceed without the unexpected-keyword exception.
- `get_staging_manager(tmp_path, use_comprehensive=False)` must continue selecting the legacy simple pipeline manager. The adapter change must not alter that factory branch.

## Expected Behavior

### Correct Behavior Specification

```text
FUNCTION expectedBehavior(result, requested_flag)
  INPUT: result of constructing CompatibleStagingManager with requested_flag
  OUTPUT: boolean

  RETURN result.is_adapter_instance
         AND result.comprehensive_manager.require_human_approval == requested_flag
         AND no_unexpected_keyword_error_was_raised
END FUNCTION
```

### Preservation Requirements

**Unchanged Behaviors:**

- Construction with no arguments or with only `staging_path` must continue to work, with the adapter defaulting to `require_human_approval=True`.
- The public `StagingManager` alias in `src/ingestor/staging_adapter.py` must continue to resolve to `CompatibleStagingManager` for existing imports.
- `add_record`, `get_pending_review`, `mark_as_reviewed`, `get_stats`, and all proxy methods must continue delegating through the compatibility adapter as before.
- With the flag set to `True`, valid extracted triples must remain pending until an attributed approval action occurs.
- With the flag set to `False`, the comprehensive backend’s existing non-human-approval behavior for valid triples must remain available.
- The `use_comprehensive=False` factory branch must continue to return the legacy pipeline staging manager.
- The Surgeon’s Table must continue to render, stage extracted records, and expose its existing edit, approve, reject, and explicit auto-approve actions.

**Scope:**

Inputs that do not exercise the incompatible adapter keyword must be unaffected. This includes no-argument construction, staging-path-only construction, legacy factory selection, record/review/statistics operations, non-constructor pipeline behavior, and all existing UI interactions after the pipeline has been initialized. The `views/` package contains only `views/__init__.py` and has no staging call sites; the active UI implementation is `components/surgeons_table.py`.

## Hypothesized Root Cause

1. **Adapter signature mismatch**: `CompatibleStagingManager.__init__` currently declares only `staging_path`, so Python rejects `require_human_approval` before any backend initialization.

2. **Backend name shadowing**: `src/ingestor/staging_adapter.py` imports the comprehensive class as `StagingManager`, then later assigns `StagingManager = CompatibleStagingManager` for public compatibility. An unqualified `StagingManager(...)` inside the adapter therefore resolves to the adapter itself at runtime. Adding only the missing parameter would risk recursive adapter construction rather than reliably reaching the comprehensive backend.

3. **Different defaults at the two layers**: The comprehensive backend defaults `require_human_approval` to `False`, while this adapter already passes `True` intentionally for the compliance-oriented UI path. The adapter’s new public default must remain `True` rather than inheriting the backend default.

4. **Extraction-path exposure**: `IngestionPipeline` constructs the comprehensive adapter through `get_staging_manager`, and `components/surgeons_table.py` starts that pipeline when the user uploads a PDF. A constructor error therefore prevents extraction before PDF processing and staging begin.

## Correctness Properties

Property 1: Bug Condition - Approval Flag Is Accepted and Propagated

_For any_ boolean `requested_flag` and valid staging path where `isBugCondition` identifies the adapter construction as incompatible, the fixed `CompatibleStagingManager` constructor SHALL accept the keyword without raising `TypeError`, create the adapter, and set `comprehensive_manager.require_human_approval` to exactly `requested_flag`; the public `StagingManager` alias SHALL have the same behavior.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Existing Construction and Approval Behavior

_For any_ input where the bug condition does NOT hold, the fixed adapter SHALL produce the same compatibility behavior as the original implementation, including no-argument and staging-path-only construction, delegation of adapter methods, legacy factory selection, and the comprehensive backend’s existing pending-versus-auto-approval behavior for `True` and `False` approval modes.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct:

**File**: `src/ingestor/staging_adapter.py`

**Functions/Symbols**: module import binding and `CompatibleStagingManager.__init__`

**Specific Changes**:

1. **Keep a stable comprehensive-backend reference**: Import the implementation from `src.staging_manager` under a distinct name such as `ComprehensiveStagingManager`, or bind it to a private module-level name before the public compatibility alias is assigned. This prevents `StagingManager = CompatibleStagingManager` from changing the class referenced by the adapter’s backend construction.

2. **Extend the adapter constructor compatibly**: Change the signature to preserve `staging_path` as the first and only required positional-compatible parameter, then add `require_human_approval: bool = True`. Do not remove or reorder the existing `staging_path` argument.

3. **Forward the exact setting**: Construct the comprehensive backend through the stable backend reference and pass `staging_path` and `require_human_approval` explicitly. Do not coerce, invert, or replace the caller’s boolean value.

4. **Preserve the public alias and factory contract**: Leave `StagingManager = CompatibleStagingManager` and the `use_comprehensive` factory branch intact. Existing callers then gain the new optional keyword without changing their imports or call shape.

5. **Do not modify unrelated layers**: No source changes are needed in `src/staging_manager.py`, `src/ingestor/pipeline.py`, `app.py`, `components/surgeons_table.py`, or `views/__init__.py`. Their existing calls should be validated against the corrected adapter. If a future requirement is to configure the flag from pipeline configuration, that should be a separate change rather than part of this constructor-compatibility fix.

### Test Changes Planned

1. Add focused adapter tests, preferably in `tests/test_staging_adapter.py`, using `tmp_path` and isolated backend paths. Cover the default constructor, explicit `True`, explicit `False`, and the public alias.
2. Assert propagation by inspecting `adapter.comprehensive_manager.require_human_approval`, rather than only checking that construction succeeds.
3. Add an approval-mode test with a valid `ExtractedTriple`: `True` leaves it pending, while `False` permits the existing backend auto-approval path. This protects the exact semantic effect of propagation.
4. Add an extraction-path regression test that exercises `IngestionPipeline` construction or the Surgeon’s Table pipeline factory with the staging adapter path isolated. The test must demonstrate that initialization reaches a usable staging manager and that a representative processed/staged record can pass through without the unexpected-keyword exception.
5. Reuse existing `tests/test_surgeons_table.py` helper conventions and the integration test’s injected doubles where possible. Do not require a real Streamlit session, Ollama service, or persistent repository data for this constructor regression.

## Testing Strategy

### Validation Approach

The testing strategy follows the bug-condition workflow: first demonstrate the constructor incompatibility on the unfixed implementation, then verify that every supported approval value is accepted and forwarded, and finally check that existing adapter, pipeline, and Surgeon’s Table behavior remains unchanged. Tests should use temporary staging and approved-graph paths so they do not mutate `data/`.

### Exploratory Bug Condition Checking

**Goal**: Surface a concrete counterexample on the unfixed adapter and confirm both parts of the root-cause analysis.

**Test Plan**: Before applying the source fix, instantiate the adapter with `True` and `False`, and exercise the public alias. Record the unexpected-keyword `TypeError`. If the signature is temporarily made permissive during investigation, verify that an unaliased comprehensive reference is necessary because the bottom-level public alias otherwise causes recursive/self construction.

**Test Cases**:

1. **Explicit true flag**: Construct `CompatibleStagingManager(tmp_path, require_human_approval=True)` and observe the unexpected-keyword failure on the unfixed code.
2. **Explicit false flag**: Construct `CompatibleStagingManager(tmp_path, require_human_approval=False)` and observe the same failure.
3. **Public alias**: Construct `staging_adapter.StagingManager(tmp_path, require_human_approval=True)` and confirm the compatibility import is covered.
4. **Surgeon’s Table startup**: Start the pipeline path used by `components.surgeons_table.render_surgeons_table` and confirm the failure occurs during staging-manager construction before extraction can stage records.

**Expected Counterexamples**:

- Python raises `TypeError` for the unexpected `require_human_approval` keyword.
- The extraction flow cannot obtain a staging manager and reports PDF extraction failure before normal staging behavior.
- If only the signature is widened without fixing the import binding, adapter construction can recurse because the public alias shadows the comprehensive class.

### Fix Checking

**Goal**: Verify that every input satisfying the bug condition gets the required constructor and backend behavior.

**Pseudocode:**

```text
FOR requested_flag IN [True, False] DO
  result := CompatibleStagingManager(temp_path, require_human_approval=requested_flag)
  ASSERT expectedBehavior(result, requested_flag)
  ASSERT result.comprehensive_manager.require_human_approval == requested_flag
END FOR

alias_result := staging_adapter.StagingManager(temp_path, require_human_approval=True)
ASSERT expectedBehavior(alias_result, True)

pipeline_result := SurgeonTablePipelineFactoryWithIsolatedStaging()
ASSERT pipeline_result.staging_manager is usable
ASSERT no unexpected-keyword error was raised
```

### Preservation Checking

**Goal**: Verify that inputs outside the constructor incompatibility retain the original compatibility and approval behavior.

**Pseudocode:**

```text
FOR construction IN [
  CompatibleStagingManager(),
  CompatibleStagingManager(temp_path),
  get_staging_manager(temp_path, use_comprehensive=True),
  get_staging_manager(temp_path, use_comprehensive=False)
] DO
  ASSERT construction preserves its original factory and compatibility contract
END FOR

FOR requested_flag IN [True, False] DO
  manager := CompatibleStagingManager(temp_path, require_human_approval=requested_flag)
  record_id := manager.add_record(valid_staging_record)
  ASSERT approval_state_matches_existing_backend_mode(manager, record_id, requested_flag)
END FOR

ASSERT existing Surgeon’s Table row, edit, approval, rejection, and statistics helpers
       retain their current outcomes with an isolated manager
```

**Testing Approach**: Use unit tests for constructor and backend propagation, property-based tests for the boolean and construction-form matrix, and integration tests for the ingestion pipeline entry point used by the Surgeon’s Table. Preserve the current tests that cover table transformations and HITL actions. The new tests should isolate filesystem state with `tmp_path` and mock or inject expensive extraction dependencies.

### Unit Tests

- Construct `CompatibleStagingManager(tmp_path)` and assert successful initialization with backend flag `True`.
- Construct with explicit `require_human_approval=True` and `False`; assert successful initialization and exact backend propagation.
- Construct through the public `staging_adapter.StagingManager` alias and assert it remains the compatibility adapter.
- Verify a valid staged record remains pending under `True` and follows existing auto-approval behavior under `False`.
- Verify the existing adapter delegation methods and `use_comprehensive=False` factory branch are unchanged.

### Property-Based Tests

- Generate `require_human_approval` from the boolean domain and assert construction succeeds and the backend stores the generated value exactly.
- Generate supported construction forms with either no staging path or a temporary staging path and assert the default remains `True` when the keyword is omitted.
- Generate valid staging records and approval modes, then assert the record’s pending/approved outcome matches the comprehensive backend’s pre-existing mode semantics.
- Include the public alias in the generated constructor path so symbol-shadowing regressions cannot be hidden by testing only the class name.

### Integration Tests

- Exercise `IngestionPipeline` initialization with an isolated staging path and assert its `staging_manager` is a usable `CompatibleStagingManager` without the unexpected-keyword exception.
- Exercise the Surgeon’s Table extraction path with a lightweight pipeline factory or injected pipeline double, then verify a representative extraction can reach staging and the existing table helpers can read the result.
- Run the existing pipeline and Surgeon’s Table test suites plus `pytest -q` to confirm no regression in PDF processing, staging, approval, editing, rejection, or UI table behavior.
