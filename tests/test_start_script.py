"""Focused tests for the Hugging Face Spaces startup script."""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = PROJECT_ROOT / "start.sh"


def _write_executable(path: Path, content: str) -> None:
    """Write an executable fake command used by startup integration tests."""
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _base_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Create isolated runtime paths and fake command locations."""
    bin_dir = tmp_path / "bin"
    app_dir = tmp_path / "app"
    bin_dir.mkdir()
    app_dir.mkdir()

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "APP_DIR": str(app_dir),
            "OLLAMA_STARTUP_TIMEOUT": "5",
            "OLLAMA_POLL_INTERVAL": "0.05",
            "STARTUP_LOG_FILE": str(app_dir / "startup.log"),
            "OLLAMA_LOG_FILE": str(app_dir / "ollama.log"),
        }
    )
    return environment, bin_dir


def _ollama_command(bin_dir: Path, *, cached: bool = False, pull_fails: bool = False) -> None:
    """Install a fake Ollama command that records pull behavior."""
    cache_output = (
        "printf '%s\\n' 'NAME ID SIZE MODIFIED' 'qwen2.5:3b abc 1 GB now'"
        if cached
        else "printf '%s\\n' 'NAME ID SIZE MODIFIED'"
    )
    pull_behavior = (
        "exit 7"
        if pull_fails
        else "printf '%s\\n' \"$2\" > \"$OLLAMA_PULL_MARKER\""
    )
    _write_executable(
        bin_dir / "ollama",
        f"""#!/usr/bin/env bash
set -eu
case "${{1:-}}" in
  serve)
    exec python3 -c 'import time; time.sleep(60)'
    ;;
  list)
    {cache_output}
    ;;
  pull)
    {pull_behavior}
    ;;
  *)
    exit 2
    ;;
esac
""",
    )


def _streamlit_command(bin_dir: Path) -> None:
    """Install a fake Streamlit command that records its invocation."""
    _write_executable(
        bin_dir / "streamlit",
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "${OLLAMA_MODELS}|${HF_HOME}|$*" > "${STREAMLIT_MARKER}"
exec python3 -c 'import time; time.sleep(60)'
""",
    )


def _curl_command(bin_dir: Path, *, succeeds: bool = True) -> None:
    """Install a fake readiness probe command."""
    result = "exit 0" if succeeds else "exit 22"
    _write_executable(bin_dir / "curl", f"#!/usr/bin/env bash\n{result}\n")


def _run_until_marker(
    environment: dict[str, str], marker: Path, *, timeout: float = 5
) -> subprocess.Popen[str]:
    """Start the script and wait until Streamlit has been launched."""
    process = subprocess.Popen(
        ["bash", str(START_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not marker.exists():
        if process.poll() is not None:
            output = process.communicate()[0]
            raise AssertionError(f"startup script exited early: {output}")
        time.sleep(0.05)
    assert marker.exists(), process.communicate(timeout=1)[0]
    return process


def _stop_process(process: subprocess.Popen[str]) -> str:
    """Stop a running startup process and return its captured output."""
    process.terminate()
    output, _ = process.communicate(timeout=5)
    return output


def test_start_script_is_executable_and_has_bash_syntax() -> None:
    """The deployment entrypoint is executable and syntactically valid."""
    assert START_SCRIPT.stat().st_mode & stat.S_IXUSR
    result = subprocess.run(
        ["bash", "-n", str(START_SCRIPT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_startup_prepares_environment_pulls_model_and_launches_streamlit(
    tmp_path: Path,
) -> None:
    """Startup waits for Ollama, pulls a missing model, and starts Streamlit."""
    environment, bin_dir = _base_environment(tmp_path)
    pull_marker = tmp_path / "pull.txt"
    streamlit_marker = tmp_path / "streamlit.txt"
    environment.update(
        {
            "OLLAMA_PULL_MARKER": str(pull_marker),
            "STREAMLIT_MARKER": str(streamlit_marker),
        }
    )
    _ollama_command(bin_dir)
    _curl_command(bin_dir)
    _streamlit_command(bin_dir)

    process = _run_until_marker(environment, streamlit_marker)
    output = _stop_process(process)

    assert process.returncode == 143
    assert pull_marker.read_text(encoding="utf-8").strip() == "qwen2.5:3b"
    streamlit_args = streamlit_marker.read_text(encoding="utf-8")
    assert environment["APP_DIR"] + "/.ollama/models" in streamlit_args
    assert environment["APP_DIR"] + "/.cache" in streamlit_args
    assert "--server.port=7860" in streamlit_args
    assert "--server.address=0.0.0.0" in streamlit_args
    assert (Path(environment["APP_DIR"]) / ".ollama" / "models").is_dir()
    assert (Path(environment["APP_DIR"]) / ".cache").is_dir()
    assert (Path(environment["APP_DIR"]) / "data").is_dir()
    startup_log = Path(environment["STARTUP_LOG_FILE"]).read_text(encoding="utf-8")
    assert "Ollama is ready" in startup_log
    assert "Starting Streamlit" in startup_log
    assert "Stopping Ollama" in output or "Stopping Ollama" in startup_log


def test_startup_skips_pull_for_cached_model(tmp_path: Path) -> None:
    """Startup does not download qwen2.5:3b when Ollama already lists it."""
    environment, bin_dir = _base_environment(tmp_path)
    pull_marker = tmp_path / "pull.txt"
    streamlit_marker = tmp_path / "streamlit.txt"
    environment.update(
        {
            "OLLAMA_PULL_MARKER": str(pull_marker),
            "STREAMLIT_MARKER": str(streamlit_marker),
        }
    )
    _ollama_command(bin_dir, cached=True)
    _curl_command(bin_dir)
    _streamlit_command(bin_dir)

    process = _run_until_marker(environment, streamlit_marker)
    _stop_process(process)

    assert not pull_marker.exists()
    startup_log = Path(environment["STARTUP_LOG_FILE"]).read_text(encoding="utf-8")
    assert "already cached" in startup_log


def test_startup_fails_when_ollama_model_pull_fails(tmp_path: Path) -> None:
    """A failed model pull stops startup instead of launching Streamlit."""
    environment, bin_dir = _base_environment(tmp_path)
    streamlit_marker = tmp_path / "streamlit.txt"
    environment["STREAMLIT_MARKER"] = str(streamlit_marker)
    _ollama_command(bin_dir, pull_fails=True)
    _curl_command(bin_dir)
    _streamlit_command(bin_dir)

    result = subprocess.run(
        ["bash", str(START_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert not streamlit_marker.exists()
    startup_log = Path(environment["STARTUP_LOG_FILE"]).read_text(encoding="utf-8")
    assert "Failed to pull Ollama model" in startup_log
