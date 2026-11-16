# Bugfix Requirements Document

## Introduction

This bugfix corrects the unsupported trigger name in the Kiro hook configuration. The affected configuration is `.kiro/hooks/auto-commit.json`, which currently declares `PostTaskExecution` even though the supported v1 trigger is `PostTaskExec`. The invalid value causes the hook-schema test to fail before the hook configuration can be accepted. The scope is limited to correcting that hook trigger; no implementation code, hook commands, matchers, or unrelated hook configurations are to be changed.

The bug condition is any validation of the affected hook configuration while its trigger is `PostTaskExecution`. The fix property is that the affected hook uses the supported `PostTaskExec` trigger and passes schema validation. Acceptance requires the focused hook test command to pass all 150 tests, while regression verification confirms that the other supported hook schema fields and existing hook configurations remain unchanged.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the Kiro hook schema validator reads `.kiro/hooks/auto-commit.json` THEN the system finds the unsupported trigger value `PostTaskExecution` instead of the supported v1 trigger `PostTaskExec`.

1.2 WHEN `PYTHONPATH=. pytest tests/test_kiro_hooks.py` runs against the current hook configurations THEN `test_all_json_hooks_use_supported_v1_schema` fails because `PostTaskExecution` is not in the supported trigger set.

### Expected Behavior (Correct)

2.1 WHEN the Kiro hook schema validator reads `.kiro/hooks/auto-commit.json` THEN the system SHALL find the supported v1 trigger `PostTaskExec` for the task-completion hook.

2.2 WHEN `PYTHONPATH=. pytest tests/test_kiro_hooks.py` runs after the configuration correction THEN the system SHALL pass all 150 tests, including `test_all_json_hooks_use_supported_v1_schema`.

2.3 WHEN the corrected hook configuration is loaded THEN the system SHALL preserve its v1 schema, task-completion purpose, command action, timeout, and existing command path while changing only the invalid trigger name.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN any other JSON hook in `.kiro/hooks/` is validated THEN the system SHALL CONTINUE TO accept its existing supported trigger and v1 schema fields without requiring unrelated configuration changes.

3.2 WHEN the auto-commit hook is invoked by the supported task-completion event THEN the system SHALL CONTINUE TO use its existing command action and timeout behavior.

3.3 WHEN the focused hook test suite checks portable runner commands, ontology validation wiring, matchers, and action fields THEN the system SHALL CONTINUE TO pass those checks without changes to `tests/test_kiro_hooks.py` or hook scripts.
