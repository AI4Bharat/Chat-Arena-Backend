"""
Locust Extreme Load Test Configuration
Web UI test for up to 1500 users

Run: locust -f stress_test_locust_extreme.py --host=http://localhost:8002
Open: http://localhost:8089
Set: 1500 users, 50 spawn rate
"""

from locust import HttpUser, task, between, events
import time
import json
import uuid


class StreamingUser(HttpUser):
    """User that makes streaming requests"""
    wait_time = between(0.5, 2)  # Faster cycling for high load
    
    def on_start(self):
        self.session_id = str(uuid.uuid4())
        self.request_count = 0
    
    @task
    def stream_request(self):
        """Make a streaming request"""
        self.request_count += 1
        
        payload = {
            "session_id": self.session_id,
            "messages": [
                {"role": "user", "content": f"Test #{self.request_count}"}
            ]
        }
        
        start_time = time.time()
        chunks_received = 0
        first_chunk_time = None
        
        with self.client.post(
            "/api/messages/stream/",
            json=payload,
            catch_response=True,
            stream=True,
            timeout=30
        ) as response:
            
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")
                return
            
            try:
                for line in response.iter_lines():
                    if line:
                        chunks_received += 1
                        if first_chunk_time is None:
                            first_chunk_time = time.time()
                
                total_time = (time.time() - start_time) * 1000
                response.success()
                
            except Exception as e:
                response.failure(f"Stream error: {e}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("="*70)
    print("🔥 EXTREME LOAD TEST STARTED - UP TO 1500 USERS 🔥")
    print("="*70)
    print(f"Target: {environment.host}")
    print()
    print("Recommended settings:")
    print("  - Number of users: 1500")
    print("  - Spawn rate: 50 users/second")
    print("  - Run time: 5-10 minutes")
    print()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("="*70)
    print("EXTREME LOAD TEST COMPLETED")
    print("="*70)
    stats = environment.stats
    
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Total failures: {stats.total.num_failures}")
    print(f"Failure rate: {stats.total.fail_ratio*100:.2f}%")
    print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"Min response time: {stats.total.min_response_time:.2f}ms")
    print(f"Max response time: {stats.total.max_response_time:.2f}ms")
    print(f"Requests per second: {stats.total.total_rps:.2f}")
    print()
    
    if stats.total.fail_ratio < 0.05:
        print("✅ Excellent! Failure rate < 5%")
    elif stats.total.fail_ratio < 0.10:
        print("⚠️  Warning: Failure rate between 5-10%")
    else:
        print("❌ High failure rate! Server struggling.")
