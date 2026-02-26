"""
EXTREME Stress Test - Up to 1500 Concurrent Users
Tests the absolute limits of async streaming

Run: python stress_test_extreme.py
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
        """Add a test result"""
        self.results.append({
            "concurrent_level": concurrent_level,
            "duration": duration,
            "ttfb": ttfb,
            "chunks": chunks,
            "success": success
        })
    
    def get_summary(self, concurrent_level: int) -> Dict:
        """Get summary for a concurrency level"""
        level_results = [r for r in self.results if r["concurrent_level"] == concurrent_level]
        
        if not level_results:
            return {}
        
        durations = [r["duration"] for r in level_results if r["success"]]
        ttfbs = [r["ttfb"] for r in level_results if r["success"]]
        
        if not durations:
            return {
                "concurrent_level": concurrent_level,
                "total_requests": len(level_results),
                "successful": 0,
                "failed": len(level_results),
                "avg_duration": 0,
                "median_duration": 0,
                "p95_duration": 0,
                "p99_duration": 0,
                "min_duration": 0,
                "max_duration": 0,
                "avg_ttfb": 0,
                "median_ttfb": 0,
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
        }


async def single_streaming_request(
    session: aiohttp.ClientSession,
    url: str,
    request_id: int,
    concurrent_level: int,
    results: StressTestResults,
    timeout: int = 30
):
    """Make a single streaming request"""
    payload = {
        "session_id": f"extreme-test-{request_id}",
        "messages": [
            {"role": "user", "content": f"Test #{request_id}"}
        ]
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
    
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        results.add_result(concurrent_level, duration, 0, 0, False)
    except Exception as e:
        duration = time.time() - start_time
        results.add_result(concurrent_level, duration, 0, 0, False)


async def test_concurrency_level(
    url: str,
    concurrent_level: int,
    total_requests: int,
    results: StressTestResults,
    show_progress: bool = True
):
    """Test a specific concurrency level"""
    if show_progress:
        print(f"\n{'='*80}")
        print(f"Testing: {concurrent_level} concurrent users | {total_requests} total requests")
        print(f"{'='*80}")
    
    connector = aiohttp.TCPConnector(limit=concurrent_level + 50)  # Extra headroom
    timeout = aiohttp.ClientTimeout(total=60)
    
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
            if show_progress and i % (concurrent_level * 5) == 0:
                print(f"  Progress: {i}/{len(tasks)} requests...")
            await asyncio.gather(*batch, return_exceptions=True)
    
    if show_progress:
        summary = results.get_summary(concurrent_level)
        print(f"  ✅ Completed: {summary['successful']}/{summary['total_requests']} successful")


async def run_extreme_stress_test(
    base_url: str,
    concurrency_levels: List[int],
    requests_per_level: int
):
    """Run extreme stress test"""
    url = f"{base_url}/api/messages/stream/"
    results = StressTestResults()
    
    print("="*80)
    print("🔥 EXTREME ASYNC STREAMING STRESS TEST 🔥")
    print("="*80)
    print(f"Target URL: {url}")
    print(f"Concurrency levels: {concurrency_levels}")
    print(f"Requests per level: {requests_per_level}")
    print(f"Total requests: {len(concurrency_levels) * requests_per_level}")
    print()
    print("⚠️  This will push your server to its limits!")
    print()
    input("Press Enter to start the extreme test...")
    print()
    
    overall_start = time.time()
    
    # Test each concurrency level
    for level in concurrency_levels:
        level_start = time.time()
        await test_concurrency_level(url, level, requests_per_level, results, show_progress=True)
        level_duration = time.time() - level_start
        print(f"  ⏱️  Level completed in {level_duration:.1f}s")
        
        # Brief pause between levels
        await asyncio.sleep(1)
    
    total_duration = time.time() - overall_start
    
    # Print detailed summary
    print("\n" + "="*80)
    print("📊 EXTREME STRESS TEST RESULTS")
    print("="*80)
    print(f"\nTotal Test Duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)")
    print()
    
    # Summary table
    print(f"{'Concurrent':<12} {'Total':<8} {'✓ Success':<10} {'✗ Failed':<10} {'Avg(ms)':<10} {'P95(ms)':<10} {'P99(ms)':<10} {'TTFB(ms)':<10}")
    print("-" * 90)
    
    for level in concurrency_levels:
        summary = results.get_summary(level)
        if summary:
            success_rate = (summary['successful'] / summary['total_requests'] * 100) if summary['total_requests'] > 0 else 0
            color = "✅" if success_rate >= 95 else ("⚠️ " if success_rate >= 80 else "❌")
            
            print(
                f"{color} {summary['concurrent_level']:<10} "
                f"{summary['total_requests']:<8} "
                f"{summary['successful']:<10} "
                f"{summary['failed']:<10} "
                f"{summary['avg_duration']*1000:<10.0f} "
                f"{summary['p95_duration']*1000:<10.0f} "
                f"{summary['p99_duration']*1000:<10.0f} "
                f"{summary['avg_ttfb']*1000:<10.0f}"
            )
    
    print()
    print("="*80)
    print("ANALYSIS")
    print("="*80)
    
    # Find breaking point
    for i, level in enumerate(concurrency_levels):
        summary = results.get_summary(level)
        if summary:
            success_rate = (summary['successful'] / summary['total_requests'] * 100) if summary['total_requests'] > 0 else 0
            if success_rate < 95:
                print(f"⚠️  Performance degradation starts at: {level} concurrent users")
                if i > 0:
                    prev_level = concurrency_levels[i-1]
                    print(f"✅ Recommended max capacity: {prev_level} concurrent users")
                break
    else:
        print(f"✅ Server handled all {max(concurrency_levels)} concurrent users successfully!")
    
    print()
    print("Definitions:")
    print("  - Avg: Average response time")
    print("  - P95: 95th percentile (95% of requests faster than this)")
    print("  - P99: 99th percentile (99% of requests faster than this)")
    print("  - TTFB: Time To First Byte (streaming start delay)")
    print("="*80)


def main():
    """Main entry point"""
    
    BASE_URL = "http://localhost:8002"
    
    # EXTREME concurrency levels - progressive scaling
    CONCURRENCY_LEVELS = [
        1,      # Baseline
        10,     # Light
        25,     # Moderate
        50,     # Medium
        100,    # Heavy
        200,    # Very Heavy
        300,    # Extreme
        500,    # Ultra
        750,    # Insane
        1000,   # Maximum
        1250,   # Beyond limits
        1500,   # Absolute maximum
    ]
    
    # Requests per level
    REQUESTS_PER_LEVEL = 20  # 20 requests at each concurrency level
    
    print("🔥 EXTREME ASYNC STREAMING STRESS TEST 🔥")
    print()
    print("This will test:")
    print(f"  - URL: {BASE_URL}/api/messages/stream/")
    print(f"  - Concurrency levels: {len(CONCURRENCY_LEVELS)} levels")
    print(f"  - From {min(CONCURRENCY_LEVELS)} to {max(CONCURRENCY_LEVELS)} concurrent users")
    print(f"  - Requests per level: {REQUESTS_PER_LEVEL}")
    print(f"  - Total requests: {len(CONCURRENCY_LEVELS) * REQUESTS_PER_LEVEL}")
    print()
    print("⚠️  This will push your server to its absolute limits!")
    print("    Monitor CPU, memory, and network usage during the test.")
    print()
    
    # Run test
    asyncio.run(run_extreme_stress_test(
        BASE_URL,
        CONCURRENCY_LEVELS,
        REQUESTS_PER_LEVEL
    ))


if __name__ == "__main__":
    main()
