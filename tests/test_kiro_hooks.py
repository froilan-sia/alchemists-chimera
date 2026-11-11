"""Compatibility checks for repository Kiro automation hooks."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
HOOKS = ROOT / ".kiro" / "hooks"


def load_hook(name):
    """Load a hook configuration from the repository."""
    with (HOOKS / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_all_json_hooks_use_supported_v1_schema():
    """Every hook has the fields required by the Kiro hook runner."""
    for path in HOOKS.glob("*.json"):
        document = load_hook(path.name)
        assert document["version"] == "v1"
        assert document["hooks"]
        for hook in document["hooks"]:
            assert hook["name"]
            assert hook["trigger"] in {
                "PreToolUse",
                "PostToolUse",
                "SessionStart",
                "Stop",
                "UserPromptSubmit",
                "PreTaskExec",
                "PostTaskExec",
                "PreCompact",
                "PostCompact",
                "PostFileCreate",
                "PostFileSave",
                "PostFileDelete",
            }
            matcher = hook.get("matcher", ".*")
            assert isinstance(matcher, str)
            assert matcher
            assert hook["action"]["type"] == "command"
            assert hook["action"]["command"]
            assert hook.get("timeout", 60) > 0


def test_run_tests_hook_uses_portable_runner_and_full_pytest_suite():
    """The test hook delegates to the portable runner with the full suite."""
    hook = load_hook("run-tests.json")["hooks"][0]
    command = hook["action"]["command"]

    assert "run_tests.sh" in command
    assert "pytest" in command
    assert "tests/" in command
    assert "--tb=short" in command
    assert "/Users/" not in command


def test_lint_hook_uses_portable_runner_for_saved_targets():
    """The lint hook delegates interpreter selection to the runner."""
    hook = load_hook("lint-code.json")["hooks"][0]
    command = hook["action"]["command"]

    assert "lint_code.sh" in command
    assert " ." in command
    assert "/Users/" not in command


def test_ontology_hook_references_existing_validation_script():
    """Ontology hook wiring points to the checked-in validation script."""
    hook = load_hook("validate-ontology.json")["hooks"][0]
    command = hook["action"]["command"]
    script = HOOKS / "validate_ontology.sh"

    assert script.exists()
    assert script.is_file()
    assert "validate_ontology.sh" in command
    assert "$KIRO_FILE_PATH" in command
    assert hook["matcher"].endswith("\\.ttl$")
