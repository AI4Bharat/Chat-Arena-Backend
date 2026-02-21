"""
Performance Baseline Tests for Hybrid WSGI+ASGI Migration
Captures current performance metrics before migration
"""

import time
import statistics
import asyncio
import httpx
import json
from datetime import datetime
from pathlib import Path

# Test Configuration
BASE_URL = "http://localhost:8000"
RESULTS_DIR = Path("tests/performance/results")
RESULTS_DIR.mkdir(exist_ok=True)

class PerformanceTest:
    def __init__(self, name, url, method="GET", data=None, headers=None):
        self.name = name
        self.url = url
        self.method = method
        self.data = data
        self.headers = headers or {}
        self.results = {
            'latencies': [],
            'errors': 0,
            'success': 0
        }
    
    def record_request(self, latency_ms, success=True):
        """Record individual request metrics"""
        self.results['latencies'].append(latency_ms)
        if success:
            self.results['success'] += 1
        else:
            self.results['errors'] += 1
    
    def calculate_metrics(self):
        """Calculate P50, P95, P99 latencies"""
        if not self.results['latencies']:
            return None
        
        sorted_latencies = sorted(self.results['latencies'])
        total = len(sorted_latencies)
        
        return {
            'p50': sorted_latencies[int(total * 0.50)],
            'p95': sorted_latencies[int(total * 0.95)],
            'p99': sorted_latencies[int(total * 0.99)],
            'mean': statistics.mean(sorted_latencies),
            'min': min(sorted_latencies),
            'max': max(sorted_latencies),
            'total_requests': total,
            'success_rate': (self.results['success'] / total * 100) if total > 0 else 0
        }

# Define Test Scenarios
TEST_SCENARIOS = [
    # CRUD Operations (WSGI targets)
    {
        'name': 'Health Check',
        'endpoint': '/admin/login/',  # Simple endpoint
        'method': 'GET',
        'concurrent_users': 10,
        'requests_per_user': 5,
        'category': 'WSGI',
        'description': 'Quick database-free endpoint'
    },
    {
        'name': 'List AI Models',
        'endpoint': '/api/models/',
        'method': 'GET',
        'concurrent_users': 10,
        'requests_per_user': 5,
        'category': 'WSGI',
        'description': 'Database read, simple serialization'
    },
    {
        'name': 'List Chat Sessions',
        'endpoint': '/api/sessions/',
        'method': 'GET',
        'concurrent_users': 10,
        'requests_per_user': 5,
        'category': 'WSGI',
        'description': 'Database query with relationships',
        'requires_auth': True
    },
    {
        'name': 'Leaderboard Query',
        'endpoint': '/api/leaderboard/LLM/',
        'method': 'GET',
        'concurrent_users': 5,
        'requests_per_user': 3,
        'category': 'WSGI',
        'description': 'Database aggregation query'
    },
    
    # Future ASGI targets (currently WSGI)
    {
        'name': 'Message Stream (Simulated)',
        'endpoint': '/api/messages/',
        'method': 'GET',
        'concurrent_users': 5,
        'requests_per_user': 3,
        'category': 'FUTURE_ASGI',
        'description': 'Will be streaming endpoint (currently list)',
        'requires_auth': True
    },
]

def run_sync_test(test_config):
    """Run synchronous load test"""
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    print(f"\n📊 Running: {test_config['name']}")
    print(f"   Endpoint: {test_config['endpoint']}")
    print(f"   Users: {test_config['concurrent_users']}, Requests/User: {test_config['requests_per_user']}")
    
    perf_test = PerformanceTest(
        test_config['name'],
        BASE_URL + test_config['endpoint'],
        test_config.get('method', 'GET')
    )
    
    # Setup session with retry
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.3)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    total_requests = test_config['concurrent_users'] * test_config['requests_per_user']
    
    for i in range(total_requests):
        try:
            start = time.perf_counter()
            
            if test_config['method'] == 'GET':
                response = session.get(
                    BASE_URL + test_config['endpoint'],
                    timeout=30
                )
            else:
                response = session.post(
                    BASE_URL + test_config['endpoint'],
                    json=test_config.get('data', {}),
                    timeout=30
                )
            
            latency_ms = (time.perf_counter() - start) * 1000
            success = response.status_code < 400
            
            perf_test.record_request(latency_ms, success)
            
            if (i + 1) % 10 == 0:
                print(f"   Progress: {i+1}/{total_requests} requests")
        
        except Exception as e:
            perf_test.record_request(0, success=False)
            print(f"   ❌ Error: {str(e)[:50]}")
    
    metrics = perf_test.calculate_metrics()
    
    if metrics:
        print(f"   ✅ Results:")
        print(f"      P50: {metrics['p50']:.2f}ms")
        print(f"      P95: {metrics['p95']:.2f}ms")
        print(f"      P99: {metrics['p99']:.2f}ms")
        print(f"      Success Rate: {metrics['success_rate']:.1f}%")
    
    return {
        'test': test_config['name'],
        'category': test_config['category'],
        'metrics': metrics,
        'config': test_config
    }

def generate_baseline_report(all_results):
    """Generate comprehensive baseline report"""
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    report = []
    report.append("# Performance Baseline Report\n\n")
    report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Environment:** WSGI-only (pre-hybrid migration)\n")
    report.append(f"**Server:** Django development server (manage.py runserver)\n")
    report.append("**Database:** PostgreSQL (local)\n")
    report.append("**Cache:** Redis (if enabled)\n")
    report.append("---\n\n")
    
    # Summary statistics
    report.append("## Summary\n\n")
    report.append(f"**Total Tests:** {len(all_results)}\n")
    
    wsgi_tests = [r for r in all_results if r['category'] == 'WSGI']
    future_asgi = [r for r in all_results if r['category'] == 'FUTURE_ASGI']
    
    report.append(f"**WSGI Tests:** {len(wsgi_tests)}\n")
    report.append(f"**Future ASGI Tests:** {len(future_asgi)}\n\n")
    
    # WSGI Results
    report.append("---\n\n")
    report.append("## WSGI Endpoints (Current Performance)\n\n")
    report.append("These endpoints will remain on WSGI in the hybrid architecture.\n\n")
    report.append("| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | Mean (ms) | Success % |\n")
    report.append("|----------|----------|----------|----------|-----------|----------|\n")
    
    for result in wsgi_tests:
        if result['metrics']:
            m = result['metrics']
            report.append(f"| {result['test'][:30]} | {m['p50']:.1f} | {m['p95']:.1f} | {m['p99']:.1f} | {m['mean']:.1f} | {m['success_rate']:.1f}% |\n")
    
    report.append("\n")
    
    # Future ASGI Results
    if future_asgi:
        report.append("---\n\n")
        report.append("## Future ASGI Endpoints (Baseline Performance)\n\n")
        report.append("These endpoints will be migrated to ASGI for streaming/async.\n\n")
        report.append("| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | Mean (ms) | Success % |\n")
        report.append("|----------|----------|----------|----------|-----------|----------|\n")
        
        for result in future_asgi:
            if result['metrics']:
                m = result['metrics']
                report.append(f"| {result['test'][:30]} | {m['p50']:.1f} | {m['p95']:.1f} | {m['p99']:.1f} | {m['mean']:.1f} | {m['success_rate']:.1f}% |\n")
        
        report.append("\n")
    
    # Detailed results
    report.append("---\n\n")
    report.append("## Detailed Results\n\n")
    
    for result in all_results:
        report.append(f"### {result['test']}\n\n")
        report.append(f"**Category:** {result['category']}\n")
        report.append(f"**Endpoint:** `{result['config']['endpoint']}`\n")
        report.append(f"**Description:** {result['config']['description']}\n\n")
        
        if result['metrics']:
            m = result['metrics']
            report.append("**Metrics:**\n")
            report.append(f"- Total Requests: {m['total_requests']}\n")
            report.append(f"- Success Rate: {m['success_rate']:.1f}%\n")
            report.append(f"- P50 Latency: {m['p50']:.2f} ms\n")
            report.append(f"- P95 Latency: {m['p95']:.2f} ms\n")
            report.append(f"- P99 Latency: {m['p99']:.2f} ms\n")
            report.append(f"- Mean Latency: {m['mean']:.2f} ms\n")
            report.append(f"- Min Latency: {m['min']:.2f} ms\n")
            report.append(f"- Max Latency: {m['max']:.2f} ms\n\n")
    
    # Expectations for hybrid
    report.append("---\n\n")
    report.append("## Expected Improvements with Hybrid Architecture\n\n")
    report.append("### WSGI Endpoints\n")
    report.append("- **Expected Change:** ±5% (minimal impact)\n")
    report.append("- **Rationale:** WSGI endpoints unchanged, same Gunicorn configuration\n\n")
    
    report.append("### ASGI Endpoints (Streaming)\n")
    report.append("- **Expected Improvement:** 40-70% reduction in time-to-first-byte\n")
    report.append("- **Expected Improvement:** 2-5x better concurrency for streaming responses\n")
    report.append("- **Rationale:** Non-blocking I/O, concurrent external API calls\n\n")
    
    report.append("---\n\n")
    report.append("## Comparison Methodology\n\n")
    report.append("After hybrid migration:\n\n")
    report.append("1. Re-run these exact same tests\n")
    report.append("2. Compare metrics side-by-side\n")
    report.append("3. Focus on:\n")
    report.append("   - WSGI endpoints should maintain performance (±5%)\n")
    report.append("   - Streaming endpoints should show significant improvement\n")
    report.append("   - Overall system stability and error rates\n\n")
    
    report.append("---\n\n")
    report.append(f"**Baseline Saved:** `baseline_{timestamp}.json`\n")
    report.append("**Status:** Ready for hybrid migration\n")
    
    return ''.join(report), timestamp

def save_results(results, timestamp):
    """Save results as JSON for later comparison"""
    filename = RESULTS_DIR / f"baseline_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")

def main():
    """Run all baseline tests"""
    print("="*80)
    print("🚀 Performance Baseline Testing")
    print("="*80)
    print("\n⚠️  Make sure Django server is running: python manage.py runserver 8000\n")
    
    input("Press Enter to start tests...")
    
    all_results = []
    
    for scenario in TEST_SCENARIOS:
        try:
            result = run_sync_test(scenario)
            all_results.append(result)
        except KeyboardInterrupt:
            print("\n\n❌ Tests interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
    
    if all_results:
        report, timestamp = generate_baseline_report(all_results)
        
        # Save report
        report_file = RESULTS_DIR / f"baseline_report_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        # Save raw results
        save_results(all_results, timestamp)
        
        print(f"\n📊 Report saved to: {report_file}")
        print("\n" + "="*80)
        print("✅ Baseline testing complete!")
        print("="*80)
        
        return report_file
    else:
        print("\n❌ No results to save")
        return None

if __name__ == "__main__":
    main()
