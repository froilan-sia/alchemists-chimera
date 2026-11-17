"""Observation-first tests for the Ollama timeout and API startup defects."""

from __future__ import annotations

import asyncio

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
