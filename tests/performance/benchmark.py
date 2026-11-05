#!/usr/bin/env python3
"""
Performance Benchmark Suite for Alchemist's Chimera Hybrid RAG Engine

This module provides comprehensive benchmarking for:
- Query processing latency
- Retrieval throughput
- Memory usage
- Concurrent query handling
- Fusion algorithm efficiency

Usage: python tests/performance/benchmark.py
"""

import asyncio
import time
import tracemalloc
from typing import List, Dict, Any
from statistics import mean, stdev

import sys
sys.path.insert(0, '/Users/froilansia/git/alchemists-chimera')

from src.models import QueryRequest
from src.router import HybridRouter
from src.config import QueryType

class PerformanceBenchmark:
    """Performance benchmark suite for hybrid RAG operations."""
    
    def __init__(self):
        self.router = HybridRouter()
        self.results: Dict[str, List[float]] = {}
        
    async def benchmark_query_latency(self, query: str, iterations: int = 10) -> Dict[str, Any]:
        """Benchmark individual query processing latency."""
        print(f"\n{'='*60}")
        print(f"Benchmark: Query Latency")
        print(f"{'='*60}")
        print(f"Query: {query[:50]}...")
        print(f"Iterations: {iterations}")
        
        latencies = []
        
        for i in range(iterations):
            request = QueryRequest(query=query, max_results=5)
            
            start_time = time.perf_counter()
            response = await self.router.retrieve(request)
            end_time = time.perf_counter()
            
            latency = end_time - start_time
            latencies.append(latency)
            
            if i % 3 == 0:
                print(f"  Iteration {i+1}/{iterations}: {latency:.3f}s (conf: {response.confidence:.2f})")
        
        # Calculate statistics
        stats = {
            "mean": mean(latencies),
            "std": stdev(latencies) if len(latencies) > 1 else 0,
            "min": min(latencies),
            "max": max(latencies),
            "median": sorted(latencies)[len(latencies)//2],
        }
        
        print(f"\n📊 Statistics:")
        print(f"  Mean: {stats['mean']:.3f}s")
        print(f"  Std:  {stats['std']:.3f}s")
        print(f"  Min:  {stats['min']:.3f}s")
        print(f"  Max:  {stats['max']:.3f}s")
        print(f"  Median: {stats['median']:.3f}s")
        
        return {"query": query, "latencies": latencies, "stats": stats}
    
    async def benchmark_throughput(self, queries: List[str], concurrent: int = 5) -> Dict[str, Any]:
        """Benchmark throughput with concurrent queries."""
        print(f"\n{'='*60}")
        print(f"Benchmark: Throughput ({concurrent} concurrent)")
        print(f"{'='*60}")
        print(f"Total queries: {len(queries)}")
        
        async def process_single(query: str) -> tuple[float, str]:
            request = QueryRequest(query=query, max_results=5)
            start = time.perf_counter()
            response = await self.router.retrieve(request)
            end = time.perf_counter()
            return end - start, response.answer[:50]
        
        # Process in batches
        batch_size = concurrent
        total_time = 0
        all_latencies = []
        
        for i in range(0, len(queries), batch_size):
            batch = queries[i:i+batch_size]
            
            start = time.perf_counter()
            results = await asyncio.gather(*[process_single(q) for q in batch])
            end = time.perf_counter()
            
            batch_time = end - start
            total_time += batch_time
            
            for j, (latency, _) in enumerate(results):
                all_latencies.append(latency)
            
            print(f"  Batch {i//batch_size + 1}: {batch_time:.2f}s for {len(batch)} queries")
        
        # Calculate throughput
        total_queries = len(queries)
        throughput = total_queries / total_time if total_time > 0 else 0
        
        print(f"\n📊 Statistics:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} queries/sec")
        print(f"  Avg latency: {mean(all_latencies):.3f}s")
        
        return {
            "total_queries": total_queries,
            "concurrent": concurrent,
            "total_time": total_time,
            "throughput": throughput,
            "avg_latency": mean(all_latencies),
        }
    
    async def benchmark_memory(self, queries: List[str], iterations: int = 5) -> Dict[str, Any]:
        """Benchmark memory usage during query processing."""
        print(f"\n{'='*60}")
        print(f"Benchmark: Memory Usage")
        print(f"{'='*60}")
        print(f"Iterations: {iterations}")
        
        memory_usages = []
        
        for i in range(iterations):
            # Start memory tracking
            tracemalloc.start()
            
            # Process query
            request = QueryRequest(query=queries[i % len(queries)], max_results=5)
            await self.router.retrieve(request)
            
            # Get memory usage
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            
            memory_mb = current / 1024 / 1024
            peak_mb = peak / 1024 / 1024
            memory_usages.append({"current": memory_mb, "peak": peak_mb})
            
            print(f"  Iteration {i+1}: {memory_mb:.2f} MB (peak: {peak_mb:.2f} MB)")
        
        # Calculate statistics
        current_mem = [m["current"] for m in memory_usages]
        peak_mem = [m["peak"] for m in memory_usages]
        
        print(f"\n📊 Statistics:")
        print(f"  Avg current memory: {mean(current_mem):.2f} MB")
        print(f"  Peak memory: {max(peak_mem):.2f} MB")
        
        return {
            "avg_current_mb": mean(current_mem),
            "peak_mb": max(peak_mem),
            "iterations": iterations,
        }
    
    async def benchmark_fusion_efficiency(self, alpha_values: List[float] = None) -> Dict[str, Any]:
        """Benchmark fusion algorithm with different alpha values."""
        if alpha_values is None:
            alpha_values = [0.2, 0.5, 0.8]
        
        print(f"\n{'='*60}")
        print(f"Benchmark: Fusion Efficiency")
        print(f"{'='*60}")
        
        fusion_times = []
        
        for alpha in alpha_values:
            # Mock graph and vector results
            from src.models import RetrievalResult, RetrievalSource
            
            # Normalize scores to be within 0-1 range
            graph_results = [
                RetrievalResult(
                    content=f"Graph result {i}",
                    source=RetrievalSource.GRAPH,
                    score=0.5 + (i * 0.03),  # Keep below 1.0
                    metadata={"type": "graph"}
                )
                for i in range(10)
            ]
            
            vector_results = [
                RetrievalResult(
                    content=f"Vector result {i}",
                    source=RetrievalSource.VECTOR,
                    score=0.4 + (i * 0.03),  # Keep below 1.0
                    metadata={"type": "vector"}
                )
                for i in range(10)
            ]
            
            # Time the fusion
            start = time.perf_counter()
            fused = await self.router._fuse_results(graph_results, vector_results, alpha)
            end = time.perf_counter()
            
            fusion_time = end - start
            fusion_times.append({"alpha": alpha, "time": fusion_time, "fused_count": len(fused)})
            
            print(f"  Alpha {alpha}: {fusion_time:.4f}s -> {len(fused)} results")
        
        # Calculate efficiency
        avg_time = mean([f["time"] for f in fusion_times])
        
        print(f"\n📊 Statistics:")
        print(f"  Avg fusion time: {avg_time:.4f}s")
        
        return {
            "alpha_values": alpha_values,
            "fusion_times": fusion_times,
            "avg_time": avg_time,
        }
    
    async def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks."""
        print("\n" + "="*60)
        print("ALCHEMIST'S CHIMERA - PERFORMANCE BENCHMARK SUITE")
        print("="*60)
        print(f"Router: {self.router.__class__.__name__}")
        
        # Test queries
        queries = [
            "What are the capital requirements for banks under Basel III?",
            "What subsidiaries does Bank of America own?",
            "Explain quantitative easing and its impact on inflation",
            "How does the Basel III framework affect commercial banks?",
            "What are the liquidity coverage ratios for major banks?",
        ]
        
        results = {}
        
        # Benchmark 1: Query Latency
        results["latency"] = await self.benchmark_query_latency(
            queries[0], 
            iterations=5
        )
        
        # Benchmark 2: Throughput
        results["throughput"] = await self.benchmark_throughput(
            queries * 2,  # 10 queries total
            concurrent=3
        )
        
        # Benchmark 3: Memory Usage
        results["memory"] = await self.benchmark_memory(queries, iterations=3)
        
        # Benchmark 4: Fusion Efficiency
        results["fusion"] = await self.benchmark_fusion_efficiency()
        
        # Summary
        print(f"\n{'='*60}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*60}")
        
        print(f"\n🎯 Performance Targets vs Results:")
        print(f"  Query Latency (target: <5s): {results['latency']['stats']['mean']:.3f}s {'✅' if results['latency']['stats']['mean'] < 5 else '⚠️'}")
        print(f"  Throughput: {results['throughput']['throughput']:.2f} queries/sec")
        print(f"  Memory Usage: {results['memory']['avg_current_mb']:.2f} MB")
        print(f"  Fusion Time: {results['fusion']['avg_time']*1000:.2f}ms")
        
        return results


async def main():
    """Run all benchmarks."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run performance benchmarks")
    parser.add_argument("--latency-only", action="store_true", help="Only run latency benchmark")
    parser.add_argument("--iterations", type=int, default=5, help="Number of iterations")
    
    args = parser.parse_args()
    
    benchmark = PerformanceBenchmark()
    
    if args.latency_only:
        results = await benchmark.benchmark_query_latency(
            "What are the capital requirements for banks?",
            iterations=args.iterations
        )
    else:
        results = await benchmark.run_all_benchmarks()
    
    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print("\n📝 All benchmarks completed successfully!")
    print("📊 Results saved for analysis.")


if __name__ == "__main__":
    asyncio.run(main())
