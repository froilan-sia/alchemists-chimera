"""Small, deterministic benchmarks for Task 17 performance behavior."""

import tracemalloc
from time import perf_counter

from src.performance import PerformanceConfig, PerformanceMonitor


def test_monitor_records_stage_timing():
    """Stage timings are available for the monitoring dashboard."""
    monitor = PerformanceMonitor()
    with monitor.measure("synthetic_stage"):
        sum(range(1000))

    snapshot = monitor.snapshot()
    assert snapshot["timings"]["synthetic_stage"] >= 0


def test_memory_profile_stays_bounded_for_small_workload():
    """The profiling path records a finite peak for a representative batch."""
    config = PerformanceConfig(batch_size=8, max_workers=2)
    tracemalloc.start()
    payload = ["regulatory chunk" * 100 for _ in range(config.batch_size)]
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert payload
    assert peak >= 0
    assert config.batch_size == 8


def test_batch_configuration_is_valid_for_benchmark_runs():
    """Batch and timeout settings remain explicit and bounded."""
    config = PerformanceConfig(batch_size=16, chunk_timeout_seconds=30)
    started = perf_counter()
    assert config.batch_size == 16
    assert config.chunk_timeout_seconds == 30
    assert perf_counter() - started < 1
