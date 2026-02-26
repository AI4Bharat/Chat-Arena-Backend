"""
ACTUAL 1500 Simultaneous Users Test
Tests TRUE concurrent capacity with realistic LLM delays

This sends 1500 REAL requests all at once!

Run: python stress_test_actual_1500.py
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict
import json


class MassiveTestResults:
    """Store and analyze massive concurrent test results"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
    
    def add_result(self, request_id: int, duration: float, ttfb: float, chunks: int, success: bool):
        """Add a test result"""
        self.results.append({
            "request_id": request_id,
            "duration": duration,
            "ttfb": ttfb,
            "chunks": chunks,
            "success": success,
            "timestamp": time.time()
        })
    
    def get_summary(self) -> Dict:
        """Get comprehensive summary"""
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"]]
        
        if not successful:
            return {
                "total_requests": len(self.results),
                "successful": 0,
                "failed": len(failed),
                "success_rate": 0
            }
        
        durations = [r["duration"] for r in successful]
        ttfbs = [r["ttfb"] for r in successful]
        chunks = [r["chunks"] for r in successful]
        
        # Calculate percentiles
        sorted_durations = sorted(durations)
        n = len(sorted_durations)
        
        return {
            "total_requests": len(self.results),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": (len(successful) / len(self.results) * 100) if self.results else 0,
            
            # Duration stats
            "avg_duration": statistics.mean(durations),
            "median_duration": statistics.median(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "p50_duration": sorted_durations[n//2] if n > 0 else 0,
            "p75_duration": sorted_durations[int(n*0.75)] if n > 0 else 0,
            "p90_duration": sorted_durations[int(n*0.90)] if n > 0 else 0,
            "p95_duration": sorted_durations[int(n*0.95)] if n > 0 else 0,
            "p99_duration": sorted_durations[int(n*0.99)] if n > 0 else 0,
            
            # TTFB stats
            "avg_ttfb": statistics.mean(ttfbs) if ttfbs else 0,
            "median_ttfb": statistics.median(ttfbs) if ttfbs else 0,
            "min_ttfb": min(ttfbs) if ttfbs else 0,
            "max_ttfb": max(ttfbs) if ttfbs else 0,
            
            # Chunk stats
            "avg_chunks": statistics.mean(chunks) if chunks else 0,
            "total_chunks": sum(chunks),
            
            # Timing
            "total_test_duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            "requests_per_second": len(successful) / (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        }


async def single_request(
    session: aiohttp.ClientSession,
    url: str,
    request_id: int,
    results: MassiveTestResults,
    timeout: int = 120
):
    """Make a single streaming request"""
    payload = {
        "session_id": f"massive-test-{request_id}",
        "messages": [
            {"role": "user", "content": f"Explain concept #{request_id % 100}"}
        ],
        "model": "gemini-1.5-flash"
    }
    
    start_time = time.time()
    first_chunk_time = None
    chunks_received = 0
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with session.post(url, json=payload, timeout=timeout_obj) as response:
            if response.status != 200:
                results.add_result(request_id, 0, 0, 0, False)
                return
            
            async for line in response.content:
                if line:
                    chunks_received += 1
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
        
        duration = time.time() - start_time
        ttfb = (first_chunk_time - start_time) if first_chunk_time else 0
        
        results.add_result(request_id, duration, ttfb, chunks_received, True)
    
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        results.add_result(request_id, duration, 0, 0, False)
    except Exception as e:
        duration = time.time() - start_time
        results.add_result(request_id, duration, 0, 0, False)


async def test_massive_concurrent(
    url: str,
    num_users: int
):
    """Test massive concurrent users"""
    results = MassiveTestResults()
    
    print(f"\n{'='*80}")
    print(f"Testing {num_users} ACTUAL SIMULTANEOUS USERS")
    print(f"{'='*80}")
    print("Preparing connections...")
    
    # Large connector pool
    connector = aiohttp.TCPConnector(
        limit=num_users + 100,  # Extra headroom
        limit_per_host=num_users + 100,
        ttl_dns_cache=300
    )
    timeout = aiohttp.ClientTimeout(total=120)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        print(f"Creating {num_users} concurrent requests...")
        
        tasks = []
        for i in range(num_users):
            task = single_request(session, url, i, results)
            tasks.append(task)
            
            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"  Created {i + 1}/{num_users} requests...", end='\r')
        
        print(f"\n✅ All {num_users} requests created!")
        print(f"\n🚀 Launching {num_users} simultaneous requests...")
        print("This will take ~12-20 seconds with realistic LLM delays...")
        print()
        
        results.start_time = time.time()
        
        # Launch ALL at once
        await asyncio.gather(*tasks, return_exceptions=True)
        
        results.end_time = time.time()
    
    return results


async def run_actual_1500_test(base_url: str):
    """Run the actual 1500 user test with progressive levels"""
    url = f"{base_url}/api/messages/stream/"
    
    print("="*80)
    print("🔥 ACTUAL SIMULTANEOUS USERS TEST - REALISTIC LLM DELAYS 🔥")
    print("="*80)
    print()
    print("This test will send REAL concurrent requests:")
    print("  - Progressive: 100 → 250 → 500 → 750 → 1000 → 1500")
    print("  - Each request: ~10-15 seconds (realistic LLM delay)")
    print("  - All requests per level happen simultaneously")
    print()
    print("⚠️  WARNING: This is a HEAVY test!")
    print("    Your system will handle 1500 streaming connections at once")
    print()
    
    # Test levels
    LEVELS = [100, 250, 500, 750, 1000, 1500]
    
    print("Test levels:")
    for level in LEVELS:
        print(f"  - {level} simultaneous users")
    print()
    
    input("Press Enter to start the test...")
    print()
    
    overall_start = time.time()
    all_results = {}
    
    # Test each level
    for num_users in LEVELS:
        level_results = await test_massive_concurrent(url, num_users)
        all_results[num_users] = level_results
        
        summary = level_results.get_summary()
        
        print(f"\n{'='*80}")
        print(f"RESULTS: {num_users} Simultaneous Users")
        print(f"{'='*80}")
        print(f"Success Rate:    {summary['success_rate']:.1f}% ({summary['successful']}/{summary['total_requests']})")
        print(f"Total Time:      {summary['total_test_duration']:.2f}s")
        print(f"Avg Response:    {summary['avg_duration']:.2f}s")
        print(f"P50 Response:    {summary['p50_duration']:.2f}s")
        print(f"P95 Response:    {summary['p95_duration']:.2f}s")
        print(f"P99 Response:    {summary['p99_duration']:.2f}s")
        print(f"Avg TTFB:        {summary['avg_ttfb']*1000:.0f}ms")
        print(f"Throughput:      {summary['requests_per_second']:.1f} req/s")
        
        if summary['failed'] > 0:
            print(f"\n⚠️  {summary['failed']} requests failed!")
        
        print()
        
        # Pause between levels
        if num_users != LEVELS[-1]:
            print("Pausing 3 seconds before next level...")
            await asyncio.sleep(3)
    
    total_duration = time.time() - overall_start
    
    # Final summary
    print("\n" + "="*80)
    print("📊 COMPLETE TEST SUMMARY")
    print("="*80)
    print(f"\nTotal Test Duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)")
    print()
    
    # Summary table
    print(f"{'Users':<10} {'Success%':<12} {'Avg(s)':<10} {'P95(s)':<10} {'P99(s)':<10} {'TTFB(ms)':<12} {'RPS':<10} {'Status':<10}")
    print("-" * 100)
    
    for num_users in LEVELS:
        summary = all_results[num_users].get_summary()
        success_rate = summary['success_rate']
        
        if success_rate >= 99:
            status = "✅ Perfect"
        elif success_rate >= 95:
            status = "✅ Good"
        elif success_rate >= 90:
            status = "⚠️  OK"
        else:
            status = "❌ Poor"
        
        print(
            f"{num_users:<10} "
            f"{success_rate:<12.1f} "
            f"{summary['avg_duration']:<10.2f} "
            f"{summary['p95_duration']:<10.2f} "
            f"{summary['p99_duration']:<10.2f} "
            f"{summary['avg_ttfb']*1000:<12.0f} "
            f"{summary['requests_per_second']:<10.1f} "
            f"{status:<10}"
        )
    
    print()
    print("="*80)
    print("ANALYSIS")
    print("="*80)
    
    # Find maximum capacity
    max_capacity = 0
    for num_users in LEVELS:
        summary = all_results[num_users].get_summary()
        if summary['success_rate'] >= 95:
            max_capacity = num_users
    
    print(f"\n✅ Maximum Capacity: {max_capacity} simultaneous users (>95% success)")
    
    # Check if all passed
    all_passed = all(
        all_results[num].get_summary()['success_rate'] >= 95 
        for num in LEVELS
    )
    
    if all_passed:
        print(f"🎉 AMAZING! Server handled ALL {max(LEVELS)} simultaneous users successfully!")
    
    print()
    print("Definitions:")
    print("  - Success%: Percentage of requests completed successfully")
    print("  - Avg: Average response time")
    print("  - P95: 95th percentile (95% of requests faster)")
    print("  - P99: 99th percentile (99% of requests faster)")
    print("  - TTFB: Time To First Byte (ms)")
    print("  - RPS: Requests Per Second (throughput)")
    print("="*80)


def main():
    """Main entry point"""
    BASE_URL = "http://localhost:8002"
    
    print("🔥 ACTUAL 1500 SIMULTANEOUS USERS TEST 🔥")
    print()
    print("This test will:")
    print("  ✅ Send REAL 100, 250, 500, 750, 1000, 1500 simultaneous requests")
    print("  ✅ Use realistic LLM delays (10-15 seconds per response)")
    print("  ✅ Test true maximum capacity")
    print()
    print("Expected duration:")
    print("  - Each level: ~15-20 seconds (all parallel)")
    print("  - Total: ~2-3 minutes")
    print()
    print("System requirements:")
    print("  - This is HEAVY! Monitor CPU/memory")
    print("  - 1500 simultaneous connections")
    print("  - ~500MB-1GB memory usage spike")
    print()
    
    # Run test
    asyncio.run(run_actual_1500_test(BASE_URL))


if __name__ == "__main__":
    main()
