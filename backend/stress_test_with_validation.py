"""
Enhanced Stress Test with Response Validation
Tests up to 3000 concurrent users with Claude Sonnet 4
Validates responses without requiring [DONE] marker

Run: python stress_test_with_validation.py
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict
import json


class ResponseValidation:
    """Validate streaming responses"""
    
    def __init__(self):
        self.validations = []
    
    def add_validation(
        self,
        request_id: int,
        success: bool,
        chunks_received: int,
        total_bytes: int,
        has_complete_response: bool,
        response_text: str,
        error_msg: str = None
    ):
        """Record validation result"""
        self.validations.append({
            "request_id": request_id,
            "success": success,
            "chunks_received": chunks_received,
            "total_bytes": total_bytes,
            "has_complete_response": has_complete_response,
            "response_length": len(response_text),
            "response_preview": response_text[:100] if response_text else "",
            "error_msg": error_msg
        })
    
    def get_issues(self):
        """Get problematic responses"""
        issues = []
        
        for v in self.validations:
            if not v["success"]:
                issues.append({
                    "request_id": v["request_id"],
                    "issue": "Request failed",
                    "error": v["error_msg"]
                })
            elif v["chunks_received"] == 0:
                issues.append({
                    "request_id": v["request_id"],
                    "issue": "No chunks received",
                    "error": "Empty response"
                })
            elif v["chunks_received"] < 10:
                issues.append({
                    "request_id": v["request_id"],
                    "issue": "Too few chunks (incomplete stream)",
                    "chunks": v["chunks_received"],
                    "bytes": v["total_bytes"]
                })
            elif v["total_bytes"] < 1000:
                issues.append({
                    "request_id": v["request_id"],
                    "issue": "Response too small",
                    "bytes": v["total_bytes"]
                })
        
        return issues
    
    def get_summary(self):
        """Get validation summary"""
        total = len(self.validations)
        if total == 0:
            return {}
        
        successful = sum(1 for v in self.validations if v["success"])
        # Consider complete if has chunks and reasonable byte count
        complete = sum(1 for v in self.validations if v["chunks_received"] >= 10 and v["total_bytes"] >= 1000)
        has_chunks = sum(1 for v in self.validations if v["chunks_received"] > 0)
        
        chunks = [v["chunks_received"] for v in self.validations if v["success"]]
        bytes_list = [v["total_bytes"] for v in self.validations if v["success"]]
        lengths = [v["response_length"] for v in self.validations if v["success"]]
        
        return {
            "total_requests": total,
            "successful": successful,
            "complete_responses": complete,
            "has_chunks": has_chunks,
            "avg_chunks": statistics.mean(chunks) if chunks else 0,
            "avg_bytes": statistics.mean(bytes_list) if bytes_list else 0,
            "avg_response_length": statistics.mean(lengths) if lengths else 0,
            "min_chunks": min(chunks) if chunks else 0,
            "max_chunks": max(chunks) if chunks else 0,
        }


class MassiveTestResults:
    """Store test results with validation"""
    
    def __init__(self):
        self.results = []
        self.validation = ResponseValidation()
        self.start_time = None
        self.end_time = None
    
    def add_result(
        self,
        request_id: int,
        duration: float,
        ttfb: float,
        chunks: int,
        success: bool,
        total_bytes: int = 0,
        response_text: str = "",
        has_complete: bool = False,
        error_msg: str = None
    ):
        """Add test result with validation"""
        self.results.append({
            "request_id": request_id,
            "duration": duration,
            "ttfb": ttfb,
            "chunks": chunks,
            "success": success,
            "timestamp": time.time()
        })
        
        # Add validation
        self.validation.add_validation(
            request_id=request_id,
            success=success,
            chunks_received=chunks,
            total_bytes=total_bytes,
            has_complete_response=has_complete,
            response_text=response_text,
            error_msg=error_msg
        )
    
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
            "p95_duration": sorted_durations[int(n*0.95)] if n > 0 else 0,
            "p99_duration": sorted_durations[int(n*0.99)] if n > 0 else 0,
            
            # TTFB stats
            "avg_ttfb": statistics.mean(ttfbs) if ttfbs else 0,
            
            # Chunk stats
            "avg_chunks": statistics.mean(chunks) if chunks else 0,
            
            # Timing
            "total_test_duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            "requests_per_second": len(successful) / (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        }


async def single_request_with_validation(
    session: aiohttp.ClientSession,
    url: str,
    request_id: int,
    results: MassiveTestResults,
    timeout: int = 120
):
    """Make a single streaming request and validate response"""
    payload = {
        "session_id": f"validation-test-{request_id}",
        "messages": [
            {"role": "user", "content": f"Explain advanced concept #{request_id % 100}"}
        ],
        "model": "claude-sonnet-4"
    }
    
    start_time = time.time()
    first_chunk_time = None
    chunks_received = 0
    total_bytes = 0
    response_text = ""
    has_done_marker = False
    error_msg = None
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with session.post(url, json=payload, timeout=timeout_obj) as response:
            if response.status != 200:
                error_msg = f"HTTP {response.status}"
                results.add_result(
                    request_id, 0, 0, 0, False,
                    total_bytes=0,
                    response_text="",
                    has_complete=False,
                    error_msg=error_msg
                )
                return
            
            async for line in response.content:
                if line:
                    chunks_received += 1
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                    
                    # Decode chunk
                    try:
                        line_text = line.decode('utf-8').strip()
                        total_bytes += len(line)
                        
                        # Check for SSE data
                        if line_text.startswith('data: '):
                            data_content = line_text[6:]  # Remove 'data: ' prefix
                            
                            # Check for [DONE] marker
                            if data_content == '[DONE]':
                                has_done_marker = True
                            else:
                                # Try to parse JSON
                                try:
                                    json_data = json.loads(data_content)
                                    # Extract text from response
                                    if isinstance(json_data, dict):
                                        if 'content' in json_data:
                                            response_text += json_data['content']
                                        elif 'text' in json_data:
                                            response_text += json_data['text']
                                        elif 'delta' in json_data and 'content' in json_data['delta']:
                                            response_text += json_data['delta']['content']
                                except json.JSONDecodeError:
                                    # Not JSON, might be plain text
                                    response_text += data_content
                    except UnicodeDecodeError:
                        pass
        
        duration = time.time() - start_time
        ttfb = (first_chunk_time - start_time) if first_chunk_time else 0
        
        # Determine if response is complete based on chunks and bytes (not just [DONE])
        has_complete = has_done_marker or (chunks_received >= 10 and total_bytes >= 1000)
        
        results.add_result(
            request_id,
            duration,
            ttfb,
            chunks_received,
            True,
            total_bytes=total_bytes,
            response_text=response_text,
            has_complete=has_complete,
            error_msg=None
        )
    
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        error_msg = "Timeout"
        results.add_result(
            request_id, duration, 0, chunks_received, False,
            total_bytes=total_bytes,
            response_text=response_text,
            has_complete=False,
            error_msg=error_msg
        )
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        results.add_result(
            request_id, duration, 0, chunks_received, False,
            total_bytes=total_bytes,
            response_text=response_text,
            has_complete=False,
            error_msg=error_msg
        )


async def test_with_validation(url: str, num_users: int):
    """Test with response validation"""
    results = MassiveTestResults()
    
    print(f"\n{'='*80}")
    print(f"Testing {num_users} Users with Response Validation")
    print(f"{'='*80}")
    
    connector = aiohttp.TCPConnector(
        limit=num_users + 100,
        limit_per_host=num_users + 100,
        ttl_dns_cache=300
    )
    timeout = aiohttp.ClientTimeout(total=120)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        print(f"Creating {num_users} concurrent requests...")
        
        tasks = []
        for i in range(num_users):
            task = single_request_with_validation(session, url, i, results)
            tasks.append(task)
        
        print(f"🚀 Launching {num_users} requests with validation...")
        results.start_time = time.time()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        results.end_time = time.time()
    
    return results


async def run_validation_test(base_url: str):
    """Run test with comprehensive validation up to 3000 users"""
    url = f"{base_url}/api/messages/stream/"
    
    print("="*80)
    print("🔍 STRESS TEST WITH RESPONSE VALIDATION - CLAUDE SONNET 4")
    print("="*80)
    print()
    print("This test validates:")
    print("  ✅ Request success")
    print("  ✅ Chunks received (minimum 10 chunks expected)")
    print("  ✅ Response size (minimum 1KB expected)")
    print("  ✅ Response content length")
    print("  ✅ Error detection")
    print()
    print("Testing up to 3000 concurrent users!")
    print()
    
    # Progressive levels up to 3000
    LEVELS = [100, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 2750, 3000]
    
    print(f"Test levels: {LEVELS}")
    print(f"Total levels: {len(LEVELS)}")
    print(f"Expected duration: ~{len(LEVELS) * 20 // 60} minutes")
    print()
    
    input("Press Enter to start validation test...")
    print()
    
    overall_start = time.time()
    all_results = {}
    
    for num_users in LEVELS:
        level_results = await test_with_validation(url, num_users)
        all_results[num_users] = level_results
        
        summary = level_results.get_summary()
        val_summary = level_results.validation.get_summary()
        issues = level_results.validation.get_issues()
        
        print(f"\n{'='*80}")
        print(f"RESULTS: {num_users} Users")
        print(f"{'='*80}")
        print(f"\nPerformance:")
        print(f"  Success Rate:    {summary['success_rate']:.1f}% ({summary['successful']}/{summary['total_requests']})")
        print(f"  Avg Response:    {summary['avg_duration']:.2f}s")
        print(f"  P95 Response:    {summary['p95_duration']:.2f}s")
        print(f"  Avg TTFB:        {summary['avg_ttfb']*1000:.0f}ms")
        
        print(f"\nResponse Quality:")
        complete_pct = (val_summary['complete_responses'] / val_summary['total_requests'] * 100) if val_summary['total_requests'] > 0 else 0
        print(f"  Complete:        {val_summary['complete_responses']}/{val_summary['total_requests']} ({complete_pct:.1f}%)")
        print(f"  Avg Chunks:      {val_summary['avg_chunks']:.1f}")
        print(f"  Avg Bytes:       {val_summary['avg_bytes']:.0f}")
        print(f"  Avg Length:      {val_summary['avg_response_length']:.0f} chars")
        
        if issues:
            print(f"\n⚠️  Issues Found: {len(issues)}")
            print(f"\nFirst 5 issues:")
            for issue in issues[:5]:
                print(f"  - Request #{issue['request_id']}: {issue['issue']}")
                if 'error' in issue:
                    print(f"    Error: {issue['error']}")
                elif 'chunks' in issue:
                    print(f"    Chunks: {issue['chunks']}, Bytes: {issue['bytes']}")
        else:
            print(f"\n✅ No issues found - All responses valid!")
        
        print()
        
        if num_users != LEVELS[-1]:
            await asyncio.sleep(2)
    
    total_duration = time.time() - overall_start
    
    # Final summary
    print("\n" + "="*80)
    print("📊 VALIDATION SUMMARY")
    print("="*80)
    print()
    
    print(f"{'Users':<10} {'Success%':<12} {'Complete%':<12} {'Avg Chunks':<12} {'Avg Bytes':<12} {'Issues':<10}")
    print("-" * 80)
    
    for num_users in LEVELS:
        summary = all_results[num_users].get_summary()
        val_summary = all_results[num_users].validation.get_summary()
        issues = all_results[num_users].validation.get_issues()
        
        complete_pct = (val_summary['complete_responses'] / val_summary['total_requests'] * 100) if val_summary['total_requests'] > 0 else 0
        
        status = "✅" if complete_pct >= 95 else "⚠️ "
        
        print(
            f"{status} {num_users:<8} "
            f"{summary['success_rate']:<12.1f} "
            f"{complete_pct:<12.1f} "
            f"{val_summary['avg_chunks']:<12.1f} "
            f"{val_summary['avg_bytes']:<12.0f} "
            f"{len(issues):<10}"
        )
    
    print()
    print("="*80)
    print("QUALITY ASSESSMENT")
    print("="*80)
    
    all_issues = []
    for num_users in LEVELS:
        all_issues.extend(all_results[num_users].validation.get_issues())
    
    if not all_issues:
        print("\n🎉 PERFECT! All responses were complete and valid!")
        print("   ✅ Every request got an appropriate response")
        print("   ✅ All responses had proper chunks (10+)")
        print("   ✅ All responses had complete content (1KB+)")
        print(f"\n✅ Your system handled {max(LEVELS)} concurrent users perfectly!")
    else:
        print(f"\n⚠️  Found {len(all_issues)} responses with issues")
        print("\nIssue breakdown:")
        
        issue_types = {}
        for issue in all_issues:
            issue_type = issue['issue']
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        for issue_type, count in issue_types.items():
            print(f"  - {issue_type}: {count}")
    
    print()
    print(f"Total test duration: {total_duration/60:.1f} minutes")
    print("="*80)


def main():
    BASE_URL = "http://localhost:8002"
    
    print("🔍 STRESS TEST WITH RESPONSE VALIDATION")
    print()
    print("Configuration:")
    print("  • Model: claude-sonnet-4")
    print("  • Test range: 100 → 3000 concurrent users")
    print("  • Levels: 13 progressive steps")
    print("  • Validation: Chunks + Bytes (no [DONE] required)")
    print()
    print("This enhanced test will:")
    print("  ✅ Verify each response is complete")
    print("  ✅ Count chunks and bytes received")
    print("  ✅ Detect incomplete/failed responses")
    print("  ✅ Show detailed quality metrics")
    print("  ✅ Test up to 3000 simultaneous users!")
    print()
    
    asyncio.run(run_validation_test(BASE_URL))


if __name__ == "__main__":
    main()
