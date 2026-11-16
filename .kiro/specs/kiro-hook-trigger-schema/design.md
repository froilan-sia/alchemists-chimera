# Kiro Hook Trigger Schema Bugfix Design

## Overview

The Kiro hook schema test rejects `.kiro/hooks/auto-commit.json` because its task-completion hook declares the unsupported v1 trigger `PostTaskExecution`. The supported trigger name in the repository's schema test is `PostTaskExec`.

The minimal fix is a one-value configuration change in `.kiro/hooks/auto-commit.json`: replace `PostTaskExecution` with `PostTaskExec`. No Python implementation files, hook scripts, action commands, timeout values, descriptions, matchers, or other hook configurations are in scope. Validation will use `PYTHONPATH=. pytest tests/test_kiro_hooks.py` after the configuration change and must pass all 150 tests.

## Glossary

- **Bug_Condition (C)**: A validation or hook-loading scenario in which `.kiro/hooks/auto-commit.json` contains the unsupported trigger `PostTaskExecution`.
- **Property (P)**: The corrected auto-commit hook uses the supported v1 trigger `PostTaskExec` and passes the repository's hook-schema validation.
- **Preservation**: Every unrelated hook field and behavior remains unchanged, including the auto-commit command and timeout, the other JSON hook configurations, hook scripts, matchers, and schema checks.
- **Affected hook**: The hook named `Commit Changes After Task Completion` in `.kiro/hooks/auto-commit.json`.
- **Supported v1 trigger**: A trigger value accepted by `tests/test_kiro_hooks.py`, including `PostTaskExec`.
- **Focused hook test suite**: `PYTHONPATH=. pytest tests/test_kiro_hooks.py`, which validates the JSON hook schema and related hook wiring.

## Bug Details

### Bug Condition

The bug manifests when the repository validates the task-completion hook in `.kiro/hooks/auto-commit.json`. The hook's `trigger` field is `PostTaskExecution`, but the supported v1 trigger is `PostTaskExec`. The schema test therefore rejects the configuration before the hook can be accepted.

Repository inspection identified `.kiro/hooks/auto-commit.json` as the only affected hook JSON file. Its other fields are valid and are not part of the defect.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input containing a hook configuration
  OUTPUT: boolean

  RETURN input.file == ".kiro/hooks/auto-commit.json"
         AND input.hook.name == "Commit Changes After Task Completion"
         AND input.hook.trigger == "PostTaskExecution"
         AND "PostTaskExecution" NOT IN supported_v1_triggers
END FUNCTION
```

### Examples

- **Current failing configuration:** The validator reads `.kiro/hooks/auto-commit.json` and sees `"trigger": "PostTaskExecution"`; `test_all_json_hooks_use_supported_v1_schema` fails because that value is absent from the supported trigger set.
- **Expected corrected configuration:** The same hook reads `"trigger": "PostTaskExec"`; its existing command action still invokes `.kiro/hooks/auto-commit.sh` with timeout `120`.
- **Unrelated file preservation:** `.kiro/hooks/lint-code.json` and `.kiro/hooks/run-tests.json` continue to use `PostFileSave` with their existing Python-file matchers and runner commands.
- **Ontology hook preservation:** `.kiro/hooks/validate-ontology.json` continues to use `PostFileSave`, the `.*\\.ttl$` matcher, and the existing `validate_ontology.sh` command with `$KIRO_FILE_PATH`.

## Expected Behavior

### Correct Behavior

The corrected task-completion hook must use the supported trigger name `PostTaskExec`. The correction must preserve the hook's task-completion purpose and all existing action behavior.

**Properties specification:**

```
FUNCTION expectedBehavior(result)
  INPUT: result of validating or loading the affected hook
  OUTPUT: boolean

  RETURN result.schema_is_valid == true
         AND result.hook.trigger == "PostTaskExec"
         AND result.hook.action.type == "command"
         AND result.hook.action.command
              == "bash \"${KIRO_WORKSPACE_ROOT:-.}/.kiro/hooks/auto-commit.sh\""
         AND result.hook.action.timeout == 120
END FUNCTION
```

### Preservation Requirements

**Unchanged Behaviors:**

- The auto-commit hook remains associated with the task-completion event, now through the supported `PostTaskExec` trigger.
- The auto-commit hook continues to execute the existing portable command path, `bash "${KIRO_WORKSPACE_ROOT:-.}/.kiro/hooks/auto-commit.sh"`.
- The auto-commit hook continues to use its existing timeout of `120` seconds.
- The `version`, hook name, description, action type, and action structure in `.kiro/hooks/auto-commit.json` remain unchanged.
- `init-env.json`, `lint-code.json`, `run-tests.json`, and `validate-ontology.json` remain byte-for-byte unchanged by this fix.
- Existing hook scripts remain unchanged. This includes portable test and lint runner behavior, ontology validation wiring, matchers, and action fields.
- The focused hook tests remain unchanged and continue to validate all supported v1 schema fields and unrelated hook behavior.

**Scope:**

Inputs and configurations outside the invalid trigger value must be unaffected. In particular, the fix must not alter mouse or application behavior, Python implementation code, shell scripts, other hook triggers, file matchers, command paths, timeouts, or test code.

## Hypothesized Root Cause

1. **Unsupported trigger spelling**: `.kiro/hooks/auto-commit.json` uses the descriptive value `PostTaskExecution`, but the repository's v1 trigger vocabulary uses the abbreviated value `PostTaskExec`.

2. **Schema vocabulary mismatch**: `tests/test_kiro_hooks.py` checks each JSON hook trigger against an explicit supported set. Because `PostTaskExecution` is not in that set, the entire focused schema test fails even though the hook's command action is otherwise valid.

3. **Configuration-only defect**: The command, action type, timeout, and task-completion intent are already correct. No implementation or script change is needed; changing the trigger value is sufficient.

## Correctness Properties

Property 1: Bug Condition - Task-completion hook uses the supported trigger

_For any_ validation input where `isBugCondition(input)` returns true, the fixed configuration SHALL replace `PostTaskExecution` with `PostTaskExec` for the `Commit Changes After Task Completion` hook, and the resulting hook SHALL satisfy `expectedBehavior(result)` and schema validation.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Unrelated hook configuration and behavior remain unchanged

_For any_ validation input where `isBugCondition(input)` returns false, the fixed configuration SHALL produce the same behavior as the original configuration, preserving all unrelated hook triggers, v1 schema fields, matchers, action commands, timeouts, hook scripts, and focused-test wiring.

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

**File**: `.kiro/hooks/auto-commit.json`

**Hook**: `Commit Changes After Task Completion`

**Specific Changes**:

1. **Correct the trigger value**: Change only the `trigger` field from `PostTaskExecution` to `PostTaskExec`.
2. **Preserve the v1 schema**: Leave `version: "v1"`, the `hooks` array, hook name, description, and action object unchanged.
3. **Preserve command behavior**: Leave the existing `bash "${KIRO_WORKSPACE_ROOT:-.}/.kiro/hooks/auto-commit.sh"` command and `120`-second timeout unchanged.
4. **Avoid unrelated changes**: Do not modify `tests/test_kiro_hooks.py`, any Python implementation file, any shell hook script, or any other `.kiro/hooks/*.json` file.

## Testing Strategy

### Validation Approach

The validation strategy checks the defect directly and then checks regression behavior. The intended implementation is deliberately limited to one JSON string replacement, so the test scope focuses on proving that the affected hook enters the supported trigger set while all existing hook wiring remains intact.

The fix has not been applied in this design phase. After the one-field configuration change is made, run the exact focused command:

```
PYTHONPATH=. pytest tests/test_kiro_hooks.py
```

The expected result is all 150 tests passing, including `test_all_json_hooks_use_supported_v1_schema`.

### Exploratory Bug Condition Checking

**Goal**: Confirm the existing counterexample before applying the fix and use it to validate the root-cause hypothesis.

**Test Plan**: Inspect the loaded auto-commit hook and run the focused hook test suite against the current configuration before changing the trigger. The current configuration should expose `PostTaskExecution`, and the schema test should reject that value.

**Test Cases**:

1. **Invalid trigger detection**: Load `.kiro/hooks/auto-commit.json` and assert that the current trigger is `PostTaskExecution`, which is not in the supported v1 trigger set.
2. **Focused schema failure**: Run `PYTHONPATH=. pytest tests/test_kiro_hooks.py` before the fix and observe the failure in `test_all_json_hooks_use_supported_v1_schema` caused by `PostTaskExecution`.
3. **Affected-hook isolation**: Compare all JSON hook triggers and confirm that the invalid value occurs only in `.kiro/hooks/auto-commit.json`.
4. **Action baseline**: Record that the auto-commit command and timeout are valid before the fix, demonstrating that the trigger value is the isolated defect.

**Expected Counterexamples**:

- The schema assertion fails because `PostTaskExecution` is not an accepted v1 trigger.
- The auto-commit command itself is not expected to fail from this defect; the hook is rejected at schema validation first.

### Fix Checking

**Goal**: Verify that every input satisfying the bug condition produces the corrected supported trigger and valid schema.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := load_and_validate_hook_after_fix(input)
  ASSERT expectedBehavior(result)
  ASSERT result.hook.trigger == "PostTaskExec"
END FOR
```

**Concrete validation**: Run `PYTHONPATH=. pytest tests/test_kiro_hooks.py` after changing only the trigger value. The schema test must pass, and the complete focused suite must report 150 passing tests.

### Preservation Checking

**Goal**: Verify that inputs outside the invalid trigger value retain their original behavior.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original_unrelated_configuration(input)
         == fixed_unrelated_configuration(input)
  ASSERT original_hook_behavior(input)
         == fixed_hook_behavior(input)
END FOR
```

**Testing Approach**: Use the focused hook suite as the regression check. Its schema test continues to validate every JSON hook, while the remaining tests verify portable runner commands, lint wiring, ontology validation wiring, matchers, action fields, and the absence of machine-specific command paths. Review the diff to confirm that only the trigger string in `.kiro/hooks/auto-commit.json` changed.

**Test Cases**:

1. **Other hook schema preservation**: Confirm that `init-env.json`, `lint-code.json`, `run-tests.json`, and `validate-ontology.json` retain their existing supported triggers and v1 fields.
2. **Auto-commit action preservation**: Confirm that the auto-commit command, action type, description, hook name, and timeout remain unchanged after the trigger correction.
3. **Runner and matcher preservation**: Confirm that the focused tests for `run_tests.sh`, `lint_code.sh`, `validate_ontology.sh`, Python-file matchers, and TTL-file matchers continue to pass.

### Unit Tests

- Run `test_all_json_hooks_use_supported_v1_schema` through `PYTHONPATH=. pytest tests/test_kiro_hooks.py` and verify that `PostTaskExec` is accepted.
- Verify the affected hook retains its command action, portable workspace-root path, and positive `120`-second timeout.
- Verify each unrelated hook retains its original trigger, matcher where applicable, action type, command, and timeout.

### Property-Based Tests

- Generate or enumerate supported v1 trigger values and verify that the corrected auto-commit trigger is a member of the supported set while the invalid `PostTaskExecution` value is absent.
- Compare unrelated fields before and after the change and verify that only the affected trigger field differs.
- Exercise the set of hook JSON files and verify that every file remains a valid v1 command hook with non-empty required fields.

### Integration Tests

- Run the complete focused command `PYTHONPATH=. pytest tests/test_kiro_hooks.py` and require all 150 tests to pass.
- Validate the end-to-end configuration path from JSON loading through supported-trigger schema validation for the auto-commit hook.
- Confirm that unrelated hook integrations remain covered, including portable test and lint runners and ontology validation with its existing matcher and `$KIRO_FILE_PATH` argument.
