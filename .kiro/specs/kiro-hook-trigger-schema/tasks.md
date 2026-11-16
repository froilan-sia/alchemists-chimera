# Implementation Plan

## Overview

This plan fixes the unsupported task-completion trigger in `.kiro/hooks/auto-commit.json`. It follows the bugfix workflow by recording the unfixed counterexample, preserving unrelated hook behavior, applying the smallest configuration-only correction, running the exact focused hook test command, and confirming the complete 150-test result with no unrelated file changes.

## Tasks

- [x] 1. Write the bug-condition exploration check before the fix
  - **Property 1: Bug Condition** - Task-completion hook rejects the unsupported trigger
  - **IMPORTANT**: Perform this check against the UNFIXED configuration before changing the hook JSON.
  - **GOAL**: Surface the documented counterexample and confirm the root cause without changing source, hook, or test files.
  - Inspect `.kiro/hooks/auto-commit.json` and confirm that the `Commit Changes After Task Completion` hook currently contains `"trigger": "PostTaskExecution"`.
  - Compare the value with the supported v1 trigger set used by `tests/test_kiro_hooks.py` and record that `PostTaskExecution` is unsupported.
  - Run the focused command against the unfixed configuration and document the failure in `test_all_json_hooks_use_supported_v1_schema`.
  - **EXPECTED OUTCOME ON UNFIXED CODE**: The schema check fails because `PostTaskExecution` is not an accepted v1 trigger. This expected failure confirms the bug condition from the design.
  - Record a concrete counterexample showing the affected file, hook name, invalid trigger, and schema-test failure before marking this task complete.
  - _Bug_Condition: `isBugCondition(input)` where `input.file == ".kiro/hooks/auto-commit.json"`, the hook name is `Commit Changes After Task Completion`, and `input.hook.trigger == "PostTaskExecution"`._
  - _Requirements: 1.1, 1.2_

- [x] 2. Write the preservation checks before implementing the fix
  - **Property 2: Preservation** - Unrelated hook configuration and behavior remain unchanged
  - **IMPORTANT**: Follow observation-first methodology against the UNFIXED configuration. Do not edit test files or add replacement tests.
  - Record the auto-commit hook's existing v1 version, name, description, command action, portable command path, and `120`-second timeout.
  - Record the existing trigger, matcher, action, command, and timeout fields for `init-env.json`, `lint-code.json`, `run-tests.json`, and `validate-ontology.json`.
  - Confirm the existing hook scripts and `tests/test_kiro_hooks.py` are unchanged and identify the runner, matcher, ontology wiring, and action-field checks that must remain passing.
  - Define the preservation comparison so that only the auto-commit hook's invalid trigger value may differ after the fix.
  - **EXPECTED OUTCOME ON UNFIXED CODE**: All observed unrelated fields and configurations establish the baseline to preserve; the only intended defect is the auto-commit trigger value.
  - _Preservation: For inputs where `isBugCondition(input)` is false, preserve all unrelated triggers, v1 schema fields, matchers, action commands, timeouts, hook scripts, and focused-test wiring._
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Apply the minimal hook trigger correction

  - [x] 3.1 Update only the affected trigger value
    - Edit `.kiro/hooks/auto-commit.json` for the `Commit Changes After Task Completion` hook.
    - Replace only `"trigger": "PostTaskExecution"` with `"trigger": "PostTaskExec"`.
    - Preserve the v1 schema, hook name, description, command action, portable command path, and `120`-second timeout exactly as documented.
    - Do not modify Python implementation files, shell hook scripts, `tests/test_kiro_hooks.py`, or any other `.kiro/hooks/*.json` file.
    - _Bug_Condition: `isBugCondition(input)` identifies the affected hook while its trigger is `PostTaskExecution`._
    - _Expected_Behavior: `expectedBehavior(result)` requires schema validity, `result.hook.trigger == "PostTaskExec"`, command action type, the existing portable command, and timeout `120`._
    - _Preservation: Change no field or file outside the invalid trigger value in the affected hook._
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [x] 3.2 Run the focused hook verification
    - **Property 1: Expected Behavior** - Corrected task-completion hook passes supported-trigger validation
    - **IMPORTANT**: Re-run the existing focused validation; do not modify or replace the test.
    - Run exactly: `PYTHONPATH=. pytest tests/test_kiro_hooks.py`
    - Confirm the corrected auto-commit hook uses `PostTaskExec`, is accepted as a valid v1 command hook, and retains its existing command and timeout.
    - **EXPECTED OUTCOME**: The focused hook test command passes all 150 tests, including `test_all_json_hooks_use_supported_v1_schema`.
    - _Expected_Behavior: `expectedBehavior(result)` holds for every input satisfying the bug condition._
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Verify preservation behavior after the correction
    - **Property 2: Preservation** - Existing unrelated hook behavior remains valid
    - **IMPORTANT**: Use the same focused test run from task 3.2 and review the resulting diff; do not write new tests.
    - Confirm `init-env.json`, `lint-code.json`, `run-tests.json`, and `validate-ontology.json` remain unchanged.
    - Confirm the auto-commit action type, command path, timeout, name, description, and task-completion purpose remain unchanged.
    - Confirm runner commands, matchers, ontology validation wiring, action fields, and existing hook scripts remain unchanged.
    - **EXPECTED OUTCOME**: The focused suite continues to pass its portable-runner, matcher, ontology, action-field, and schema checks without unrelated edits.
    - _Preservation: For every non-bug-condition input, the fixed configuration preserves the original unrelated behavior._
    - _Requirements: 3.1, 3.2, 3.3_

- [~] 4. Checkpoint - Confirm the complete focused result and scope
  - Run exactly: `PYTHONPATH=. pytest tests/test_kiro_hooks.py`
  - Confirm the command reports all 150 tests passing.
  - Review the diff and workspace status to confirm the only intended change is the `PostTaskExecution` to `PostTaskExec` trigger correction in `.kiro/hooks/auto-commit.json`; no source, test, shell hook, or unrelated hook files changed.
  - Confirm the completed result satisfies the bug-condition property and all preservation requirements before closing the bugfix task.
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

## Notes

- Tasks 1 and 2 are standalone pre-fix checks and must remain before implementation task 3.
- Property 1 is expected to fail on the unfixed configuration and pass after the one-value correction.
- Property 2 records behavior that must remain unchanged and must pass after the correction.
- This task artifact does not modify source, hook, or test files; implementation work is limited to the single trigger value specified in task 3.1.
