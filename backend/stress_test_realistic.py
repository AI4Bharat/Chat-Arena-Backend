"""
Stress Test with Realistic LLM Delays
Tests performance with production-like 2-3x slower responses

Run: python stress_test_realistic.py
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict
import json


class StressTestResults:
    """Store and analyze test results"""
    
    def __init__(self):
        self.results = []
    
    def add_result(self, concurrent_level: int, duration: float, ttfb: float, chunks: int, success: bool):
        self.results.append({
            "concurrent_level": concurrent_level,
            "duration": duration,
            "ttfb": ttfb,
            "chunks": chunks,
            "success": success
        })
    
    def get_summary(self, concurrent_level: int) -> Dict:
        level_results = [r for r in self.results if r["concurrent_level"] == concurrent_level]
        
        if not level_results:
            return {}
        
        durations = [r["duration"] for r in level_results if r["success"]]
        ttfbs = [r["ttfb"] for r in level_results if r["success"]]
        chunks = [r["chunks"] for r in level_results if r["success"]]
        
        if not durations:
            return {
                "concurrent_level": concurrent_level,
                "total_requests": len(level_results),
                "successful": 0,
                "failed": len(level_results),
            }
        
        return {
            "concurrent_level": concurrent_level,
            "total_requests": len(level_results),
            "successful": sum(1 for r in level_results if r["success"]),
            "failed": sum(1 for r in level_results if not r["success"]),
            "avg_duration": statistics.mean(durations),
            "median_duration": statistics.median(durations),
            "p95_duration": statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
            "p99_duration": statistics.quantiles(durations, n=100)[98] if len(durations) >= 100 else max(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "avg_ttfb": statistics.mean(ttfbs) if ttfbs else 0,
            "median_ttfb": statistics.median(ttfbs) if ttfbs else 0,
            "avg_chunks": statistics.mean(chunks) if chunks else 0,
        }


async def single_streaming_request(
    session: aiohttp.ClientSession,
    url: str,
    request_id: int,
    concurrent_level: int,
    results: StressTestResults,
    timeout: int = 60  # Longer timeout for realistic delays
):
    """Make a single streaming request"""
    payload = {
        "session_id": f"realistic-test-{request_id}",
        "messages": [
            {"role": "user", "content": f"Explain the concept #{request_id} in detail"}
        ],
        "model": "gemini-1.5-flash"
    }
    
    start_time = time.time()
    first_chunk_time = None
    chunks_received = 0
    success = True
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with session.post(url, json=payload, timeout=timeout_obj) as response:
            if response.status != 200:
                success = False
                results.add_result(concurrent_level, 0, 0, 0, False)
                return
            
            async for line in response.content:
                if line:
                    chunks_received += 1
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
        
        duration = time.time() - start_time
        ttfb = (first_chunk_time - start_time) if first_chunk_time else 0
        
        results.add_result(concurrent_level, duration, ttfb, chunks_received, True)
    
    except Exception as e:
        duration = time.time() - start_time
        results.add_result(concurrent_level, duration, 0, 0, False)


async def test_concurrency_level(
    url: str,
    concurrent_level: int,
    total_requests: int,
    results: StressTestResults
):
    """Test a specific concurrency level"""
    print(f"\n{'='*80}")
    print(f"Testing: {concurrent_level} concurrent users | {total_requests} total requests")
    print(f"{'='*80}")
    
    connector = aiohttp.TCPConnector(limit=concurrent_level + 50)
    timeout = aiohttp.ClientTimeout(total=120)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        for i in range(total_requests):
            task = single_streaming_request(
                session, url, i, concurrent_level, results
            )
            tasks.append(task)
        
        # Run with limited concurrency
        for i in range(0, len(tasks), concurrent_level):
            batch = tasks[i:i+concurrent_level]
            await asyncio.gather(*batch, return_exceptions=True)
    
    summary = results.get_summary(concurrent_level)
    print(f"  ✅ Completed: {summary['successful']}/{summary['total_requests']} successful")


async def run_realistic_stress_test(
    base_url: str,
    concurrency_levels: List[int],
    requests_per_level: int
):
    """Run realistic stress test"""
    url = f"{base_url}/api/messages/stream/"
    results = StressTestResults()
    
    print("="*80)
    print("🔥 REALISTIC LLM DELAY STRESS TEST 🔥")
    print("="*80)
    print(f"Target URL: {url}")
    print(f"Concurrency levels: {concurrency_levels}")
    print(f"Requests per level: {requests_per_level}")
    print()
    print("⚠️  Using 2-3x SLOWER realistic LLM delays")
    print("    Expected: 2-15 seconds per request")
    print()
    input("Press Enter to start...")
    print()
    
    overall_start = time.time()
    
    for level in concurrency_levels:
        level_start = time.time()
        await test_concurrency_level(url, level, requests_per_level, results)
        level_duration = time.time() - level_start
        print(f"  ⏱️  Level completed in {level_duration:.1f}s")
        await asyncio.sleep(1)
    
    total_duration = time.time() - overall_start
    
    # Summary
    print("\n" + "="*80)
    print("📊 REALISTIC STRESS TEST RESULTS")
    print("="*80)
    print(f"\nTotal Test Duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)")
    print()
    
    print(f"{'Concurrent':<12} {'Total':<8} {'✓ Success':<10} {'✗ Failed':<10} {'Avg(s)':<10} {'P95(s)':<10} {'TTFB(ms)':<10} {'Chunks':<10}")
    print("-" * 100)
    
    for level in concurrency_levels:
        summary = results.get_summary(level)
        if summary and 'avg_duration' in summary:
            success_rate = (summary['successful'] / summary['total_requests'] * 100) if summary['total_requests'] > 0 else 0
            color = "✅" if success_rate >= 95 else ("⚠️ " if success_rate >= 80 else "❌")
            
            print(
                f"{color} {summary['concurrent_level']:<10} "
                f"{summary['total_requests']:<8} "
                f"{summary['successful']:<10} "
                f"{summary['failed']:<10} "
                f"{summary['avg_duration']:<10.2f} "
                f"{summary['p95_duration']:<10.2f} "
                f"{summary['avg_ttfb']*1000:<10.0f} "
                f"{summary.get('avg_chunks', 0):<10.0f}"
            )
    
    print()
    print("="*80)


def main():
    BASE_URL = "http://localhost:8002"
    
    # Test concurrency with realistic delays
    CONCURRENCY_LEVELS = [
        1, 5, 10, 25, 50, 100, 200, 300, 500, 750, 1000, 1500
    ]
    
    REQUESTS_PER_LEVEL = 20
    
    print("🔥 REALISTIC LLM DELAY STRESS TEST 🔥")
    print()
    print(f"  - Concurrency: {CONCURRENCY_LEVELS}")
    print(f"  - Requests per level: {REQUESTS_PER_LEVEL}")
    print(f"  - Total requests: {len(CONCURRENCY_LEVELS) * REQUESTS_PER_LEVEL}")
    print(f"  - Expected: 2-15 seconds per response (realistic LLM delays)")
    print()
    
    asyncio.run(run_realistic_stress_test(
        BASE_URL,
        CONCURRENCY_LEVELS,
        REQUESTS_PER_LEVEL
    ))


if __name__ == "__main__":
    main()
