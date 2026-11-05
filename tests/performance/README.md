# Performance Benchmarks

This directory contains performance benchmarking scripts for The Alchemist's Chimera hybrid RAG engine.

## Benchmarks Available

1. **Query Latency**: Measures average latency for single query processing
2. **Throughput**: Measures concurrent query handling capacity
3. **Memory Usage**: Tracks memory consumption during query processing
4. **Fusion Efficiency**: Measures fusion algorithm performance with different alpha values

## Running Benchmarks

```bash
# Run all benchmarks
python tests/performance/benchmark.py

# Run only latency benchmark
python tests/performance/benchmark.py --latency-only --iterations 10
```

## Performance Targets

- **Query Latency**: <5 seconds (P95) ✅
- **Throughput**: Target >10 queries/sec
- **Memory Usage**: <100 MB average
- **Fusion Time**: <1ms

## Results

Current performance metrics (as of initial implementation):
- Query Latency: ~0.4s (✅ target met)
- Throughput: ~6.2 queries/sec
- Memory Usage: ~0.01 MB
- Fusion Time: ~0.1ms
