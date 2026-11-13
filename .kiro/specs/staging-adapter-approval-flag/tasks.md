# Implementation Plan

## Overview

This plan fixes the staging adapter constructor incompatibility that blocks the Surgeon’s Table extraction path. It follows the exploratory bugfix workflow: establish the constructor failure on the unfixed code, capture behavior that must be preserved, make the smallest adapter-only source change, rerun the same regression tests, and finish with the full test suite.

## Tasks

- [x] 1. Write bug condition exploration tests before the fix
  - **Property 1: Bug Condition** - Approval flag is accepted and propagated by both adapter entry points
  - **CRITICAL**: Write and run these tests against the UNFIXED implementation before changing source code.
  - **GOAL**: Surface the constructor counterexamples and confirm whether the failure is caused by both the missing keyword parameter and the module-level backend-name shadowing described in the design.
  - Use Hypothesis to generate `requested_flag` from `st.booleans()` and exercise both `CompatibleStagingManager` and the public `src.ingestor.staging_adapter.StagingManager` alias.
  - For every generated flag and an isolated `tmp_path`, assert the expected behavior target: construction succeeds, the result is the compatibility adapter, no unexpected-keyword `TypeError` is raised, and `result.comprehensive_manager.require_human_approval == requested_flag`.
  - Add a focused Surgeon’s Table startup regression that uses an isolated staging path and the same pipeline factory seam used by `components.surgeons_table.render_surgeons_table`; prove on the unfixed code that pipeline initialization or extraction setup fails before normal staging can proceed because of the adapter constructor.
  - Keep the test independent of a real Streamlit session, Ollama service, persistent repository data, or a real PDF. Use injected/lightweight doubles where the existing Surgeon’s Table test conventions require them.
  - **EXPECTED OUTCOME ON UNFIXED CODE**: The property fails with the adapter’s unexpected-keyword/recursive construction error; the startup regression records the same failure before staging. This failure is expected and confirms the bug.
  - Document at least one concrete counterexample, including the boolean value and constructor path, before marking this task complete.
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.4_

- [x] 2. Write preservation property tests before implementing the fix
  - **Property 2: Preservation** - Existing construction forms, factory selection, approval semantics, and Surgeon’s Table helpers remain compatible
  - **IMPORTANT**: Follow observation-first methodology. Observe the UNFIXED behavior for inputs outside the explicit-flag incompatibility before finalizing assertions.
  - Add focused tests for `CompatibleStagingManager(tmp_path)` and the public alias with no `require_human_approval` keyword; the expected target is successful construction with the adapter default set to `True`.
  - Cover the staging-path-only form, the omitted/default form, `get_staging_manager(tmp_path, use_comprehensive=True)`, and `get_staging_manager(tmp_path, use_comprehensive=False)`. Assert that the legacy branch still returns the simple pipeline manager and that the comprehensive branch retains the compatibility adapter contract.
  - Use generated valid staging records and both approval modes to capture the existing backend semantics: `True` keeps valid records pending until explicit review, while `False` permits the comprehensive manager’s existing valid-triple auto-approval behavior.
  - Preserve adapter delegation coverage for record insertion, pending review, statistics, approval/rejection, editing, and export/reset proxies where the existing tests already provide suitable helpers.
  - Reuse or extend `tests/test_surgeons_table.py` helpers to verify that table rows, edits, rejection, explicit approval, and the explicit auto-approve action keep their current outcomes with an isolated manager.
  - Verify the observation tests that do not exercise the constructor defect pass on the UNFIXED code. If omitted/default adapter construction exposes the same alias-shadowing failure, record it as the overlapping root-cause observation while retaining the assertion as a post-fix preservation target; do not weaken the expected default behavior.
  - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4_

- [ ] 3. Fix the staging adapter constructor bug

  - [x] 3.1 Inspect and update `src/ingestor/staging_adapter.py`
    - Inspect the import binding and `CompatibleStagingManager.__init__` around the adapter definition before editing.
    - Bind the comprehensive implementation from `src.staging_manager` under a stable distinct name such as `ComprehensiveStagingManager`; do not let `StagingManager = CompatibleStagingManager` change the backend reference used inside the adapter.
    - Extend the constructor without changing the existing first positional parameter: `staging_path: Optional[Path] = None, require_human_approval: bool = True`.
    - Forward the exact caller-provided boolean to the stable comprehensive backend reference. Do not invert, coerce, or silently replace `True` or `False`.
    - Preserve `StagingManager = CompatibleStagingManager`, `get_staging_manager`, adapter storage, and all proxy/delegation methods. Do not change `src/staging_manager.py`, the pipeline implementation, or unrelated UI behavior.
    - Update the constructor docstring only as needed to document the new optional flag and its default.
    - _Bug_Condition: `isBugCondition(input)` where the adapter or public alias receives an explicit boolean flag and rejects it or fails to forward it because of the shadowed backend name.
    - _Expected_Behavior: `expectedBehavior(result, requested_flag)` from the design; construction succeeds and `result.comprehensive_manager.require_human_approval` equals the requested flag.
    - _Preservation: Keep omitted/staging-path-only construction defaulting to `True`, retain the public alias and factory branches, and preserve all existing adapter delegation and approval behavior.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Verify every `StagingManager` call site in `src/` and `views/`
    - Re-scan `src/` and `views/` for `StagingManager`, `CompatibleStagingManager`, `staging_adapter`, `get_staging_manager`, and `staging_manager` references after the adapter edit.
    - Confirm `src/ingestor/pipeline.py` continues to use `get_staging_manager(Path(staging_path), use_comprehensive=True)` for normal ingestion and continues to call the adapter contract (`add_record`, `get_stats`).
    - Confirm the `use_comprehensive=False` branch still selects `src.ingestor.pipeline.StagingManager` and was not redirected to the adapter.
    - Confirm `components/surgeons_table.py` continues to obtain the pipeline manager through its pipeline factory and its fallback `get_staging_manager(Path("data/staging"), use_comprehensive=True)` path; do not alter rendering or HITL actions for this constructor-only bugfix.
    - Record that `views/__init__.py` is the only file under `views/` and contains no staging call sites, so no view-layer edit is required.
    - _Requirements: 2.4, 3.1, 3.2, 3.5_

  - [ ] 3.3 Verify the bug-condition exploration tests now pass
    - **Property 1: Expected Behavior** - Approval flag is accepted and propagated by both adapter entry points
    - **IMPORTANT**: Rerun the SAME tests from task 1; do not write a replacement test.
    - Verify both generated boolean values, both constructor entry points, and the isolated Surgeon’s Table/pipeline startup path now complete without the unexpected-keyword exception.
    - Assert the backend stores the exact requested flag and the resulting manager remains usable for staging.
    - **EXPECTED OUTCOME**: Tests PASS, confirming the bug condition is fixed.
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing construction forms, factory selection, approval semantics, and Surgeon’s Table helpers remain compatible
    - **IMPORTANT**: Rerun the SAME tests from task 2; do not write new tests to avoid a regression.
    - Confirm omitted/default and staging-path-only construction use `require_human_approval=True`, explicit `False` retains auto-approval semantics, the legacy factory branch remains unchanged, and existing Surgeon’s Table helper actions retain their outcomes.
    - **EXPECTED OUTCOME**: Tests PASS, confirming no regressions outside the constructor bug.
    - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4_

- [-] 4. Checkpoint - Run the full test suite
  - Run `pytest -q` from the repository root after tasks 3.3 and 3.4 pass.
  - If `pytest` is not on `PATH`, run the repository-equivalent available command, preferably `python -m pytest -q`, and record the exact fallback command used.
  - Confirm the focused staging adapter tests, the Surgeon’s Table tests, the pipeline-related tests, and all existing tests pass together.
  - Confirm no source changes were made outside the minimal adapter fix and any focused regression-test additions required by this plan.
  - _Requirements: 3.5_

## Notes

- Tasks 1 and 2 are standalone tests and must be completed before task 3 implementation work.
- Property 1 is the bug-condition exploration property and is expected to fail on the unfixed implementation, then pass after the fix.
- Property 2 is the preservation property. Its assertions must be based on observed behavior, but the required omitted/default adapter behavior remains the target even if the current alias-shadowing defect causes that overlapping construction form to fail before the fix.
- Keep filesystem state isolated with `tmp_path`; do not mutate `data/` or require external services.
- No source implementation changes are part of creating this task artifact.
