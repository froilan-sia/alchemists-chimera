"""Observation-first tests for the Ollama timeout and API startup defects."""

from __future__ import annotations

import asyncio
import logging

import pytest

from src.api import main as api_main
from src.ingestor import baseline_loader
import src.router as router_module


@pytest.mark.asyncio
async def test_lifespan_yields_while_baseline_preload_is_pending(monkeypatch):
    """A pending baseline loader exposes the unfixed pre-yield startup block."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_to_thread(function, *args, **kwargs):
        del function, args, kwargs
        started.set()
        await release.wait()
        return {"status": "loaded"}

    def fake_bootstrap():
        return {"status": "loaded"}

    class FakeStore:
        def __init__(self, *args, **kwargs):
            del args, kwargs

    class FakeRunner:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def start(self):
            return None

        async def stop(self):
            return None

    monkeypatch.setenv("BASELINE_INGEST_ON_STARTUP", "true")
    monkeypatch.setattr(api_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(baseline_loader, "bootstrap_baseline_corpus", fake_bootstrap)
    monkeypatch.setattr(router_module, "HybridRouter", lambda: object())
    monkeypatch.setattr(api_main, "IngestionJobStore", FakeStore)
    monkeypatch.setattr(api_main, "UploadedPdfStore", FakeStore)
    monkeypatch.setattr(api_main, "AsyncIngestionJobRunner", FakeRunner)

    context = api_main.lifespan(api_main.app)
    enter_task = asyncio.create_task(context.__aenter__())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert enter_task.done(), (
            "Counterexample on unfixed code: lifespan remains pending before yield "
            "while bootstrap_baseline_corpus is blocked."
        )
    finally:
        release.set()
        await enter_task
        await context.__aexit__(None, None, None)


def _patch_lifespan_dependencies(monkeypatch, state):
    """Install deterministic service doubles for lifespan preservation tests."""

    class FakeStore:
        def __init__(self, *args, **kwargs):
            del args, kwargs

    class FakeRunner:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            state["runner"] = self

        async def start(self):
            state["started"] += 1

        async def stop(self):
            state["stopped"] += 1

    monkeypatch.setattr(router_module, "HybridRouter", lambda: object())
    monkeypatch.setattr(api_main, "IngestionJobStore", FakeStore)
    monkeypatch.setattr(api_main, "UploadedPdfStore", FakeStore)
    monkeypatch.setattr(api_main, "AsyncIngestionJobRunner", FakeRunner)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["0", "false", "no"])
async def test_disabled_baseline_flags_keep_api_lifecycle_available(monkeypatch, flag):
    """All documented disabled values skip preload and retain initialized services."""
    state = {"started": 0, "stopped": 0}

    async def fail_to_thread(*args, **kwargs):
        raise AssertionError("disabled baseline must not schedule preload")

    monkeypatch.setenv("BASELINE_INGEST_ON_STARTUP", flag)
    monkeypatch.setattr(api_main.asyncio, "to_thread", fail_to_thread)
    _patch_lifespan_dependencies(monkeypatch, state)

    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    try:
        health = await api_main.health_check()
        assert health.components["retriever"] == "initialized"
        assert api_main.job_store is not None
        assert api_main.upload_store is not None
        assert api_main.job_runner is state["runner"]
        assert state["started"] == 1
    finally:
        await context.__aexit__(None, None, None)

    assert state["stopped"] == 1
    assert api_main.job_runner is None
    assert api_main.job_store is None
    assert api_main.upload_store is None


@pytest.mark.asyncio
async def test_enabled_completed_baseline_preserves_completion_logging_and_services(
    monkeypatch, caplog
):
    """A completed baseline preload logs its result before normal service startup."""
    state = {"started": 0, "stopped": 0}
    observed = {}

    def fake_bootstrap():
        return {"status": "loaded", "documents": 2}

    async def fake_to_thread(function, *args, **kwargs):
        observed["function"] = function
        del args, kwargs
        return function()

    monkeypatch.setenv("BASELINE_INGEST_ON_STARTUP", "true")
    monkeypatch.setattr(api_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(baseline_loader, "bootstrap_baseline_corpus", fake_bootstrap)
    _patch_lifespan_dependencies(monkeypatch, state)
    caplog.set_level(logging.INFO, logger=api_main.logger.name)

    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    try:
        assert observed["function"] is fake_bootstrap
        health = await api_main.health_check()
        assert health.components["retriever"] == "initialized"
        assert state["started"] == 1
    finally:
        await context.__aexit__(None, None, None)

    assert "Baseline corpus bootstrap completed" in caplog.text
    assert "documents" in caplog.text
    assert state["stopped"] == 1


@pytest.mark.asyncio
async def test_enabled_baseline_failure_is_logged_without_tearing_down_api(
    monkeypatch, caplog
):
    """A preload exception is logged while retriever and runner remain available."""
    state = {"started": 0, "stopped": 0}

    def fake_bootstrap():
        return None

    async def fake_to_thread(function, *args, **kwargs):
        del function, args, kwargs
        raise RuntimeError("fixture preload failure")

    monkeypatch.setenv("BASELINE_INGEST_ON_STARTUP", "true")
    monkeypatch.setattr(api_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(baseline_loader, "bootstrap_baseline_corpus", fake_bootstrap)
    _patch_lifespan_dependencies(monkeypatch, state)
    caplog.set_level(logging.WARNING, logger=api_main.logger.name)

    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    try:
        health = await api_main.health_check()
        assert health.components["retriever"] == "initialized"
        assert api_main.job_runner is state["runner"]
        assert state["started"] == 1
    finally:
        await context.__aexit__(None, None, None)

    assert "Baseline corpus bootstrap skipped" in caplog.text
    assert "fixture preload failure" in caplog.text
    assert state["stopped"] == 1


@pytest.mark.asyncio
async def test_lifespan_shutdown_cancellation_still_cleans_services(monkeypatch):
    """A cancellation delivered at shutdown preserves runner cleanup semantics."""
    state = {"started": 0, "stopped": 0}

    async def fake_to_thread(function, *args, **kwargs):
        del function, args, kwargs
        return {"status": "loaded"}

    monkeypatch.setenv("BASELINE_INGEST_ON_STARTUP", "true")
    monkeypatch.setattr(api_main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(baseline_loader, "bootstrap_baseline_corpus", lambda: {})
    _patch_lifespan_dependencies(monkeypatch, state)

    context = api_main.lifespan(api_main.app)
    await context.__aenter__()
    suppressed = await context.__aexit__(
        asyncio.CancelledError,
        asyncio.CancelledError(),
        None,
    )

    assert suppressed is False
    assert state["stopped"] == 1
    assert api_main.job_runner is None
    assert api_main.job_store is None
    assert api_main.upload_store is None
