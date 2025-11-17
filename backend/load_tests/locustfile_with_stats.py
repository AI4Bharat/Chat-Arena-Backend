from locust import HttpUser, task, between, events
import json
import uuid
import random
from collections import defaultdict
import threading

# Global statistics for tracking model failures
model_stats = {
    'stream_attempts': defaultdict(int),  # How many times each model was used
    'stream_failures': defaultdict(int),   # How many times each model failed
    'model_pairs': defaultdict(int),       # Track model_a + model_b combinations
    'failed_pairs': defaultdict(int),      # Failed model pairs
}
stats_lock = threading.Lock()

def track_model_usage(model_a_name, model_b_name, model_a_id, model_b_id, failed=False):
    """Track which models are being used and which are failing"""
    with stats_lock:
        pair_key = f"{model_a_name} vs {model_b_name}"

        # Track individual model attempts
        model_stats['stream_attempts'][model_a_name] += 1
        model_stats['stream_attempts'][model_b_name] += 1

        # Track pair attempts
        model_stats['model_pairs'][pair_key] += 1

        if failed:
            # Track failures
            model_stats['stream_failures'][model_a_name] += 1
            model_stats['stream_failures'][model_b_name] += 1
            model_stats['failed_pairs'][pair_key] += 1

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print model statistics when test stops"""
    print("\n" + "="*80)
    print("MODEL FAILURE ANALYSIS")
    print("="*80)

    # Individual model statistics
    print("\n--- Individual Model Performance ---")
    print(f"{'Model Name':<40} {'Attempts':<10} {'Failures':<10} {'Failure %':<10}")
    print("-" * 80)

    for model_name in sorted(model_stats['stream_attempts'].keys()):
        attempts = model_stats['stream_attempts'][model_name]
        failures = model_stats['stream_failures'][model_name]
        failure_rate = (failures / attempts * 100) if attempts > 0 else 0
        print(f"{model_name:<40} {attempts:<10} {failures:<10} {failure_rate:<10.2f}%")

    # Model pair statistics
    print("\n--- Model Pair Performance (Most Problematic) ---")
    print(f"{'Model Pair':<60} {'Attempts':<10} {'Failures':<10} {'Failure %':<10}")
    print("-" * 80)

    # Sort by failure rate
    pair_failures = []
    for pair_name, attempts in model_stats['model_pairs'].items():
        failures = model_stats['failed_pairs'].get(pair_name, 0)
        failure_rate = (failures / attempts * 100) if attempts > 0 else 0
        pair_failures.append((pair_name, attempts, failures, failure_rate))

    # Sort by failure rate (descending) and show top 20
    pair_failures.sort(key=lambda x: x[3], reverse=True)
    for pair_name, attempts, failures, failure_rate in pair_failures[:20]:
        print(f"{pair_name:<60} {attempts:<10} {failures:<10} {failure_rate:<10.2f}%")

    # Summary
    print("\n--- Summary ---")
    total_attempts = sum(model_stats['model_pairs'].values())
    total_failures = sum(model_stats['failed_pairs'].values())
    overall_failure_rate = (total_failures / total_attempts * 100) if total_attempts > 0 else 0
    print(f"Total stream attempts: {total_attempts}")
    print(f"Total stream failures: {total_failures}")
    print(f"Overall failure rate: {overall_failure_rate:.2f}%")
    print("="*80 + "\n")

class ArenaUser(HttpUser):
    wait_time = between(1, 3)  # Simulate think time (1–3 sec gap)

    def on_start(self):
        """
        Called once when a simulated user starts.
        Authenticate here and reuse the token for all subsequent requests.
        """
        print(f"User starting - authenticating once...")
        auth_response = self.client.post(
            "/auth/anonymous/",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )

        if auth_response.status_code in [200, 201]:
            auth_data = auth_response.json()
            self.access_token = auth_data['tokens']['access']
            print(f"User authenticated successfully")
        else:
            print(f"Authentication failed: {auth_response.status_code}")
            self.access_token = None

    @task
    def create_session_and_stream(self):
        """
        Create session and stream with model tracking
        """
        if not self.access_token:
            print("No access token - skipping task")
            return

        # Step 1: Create Session
        session_payload = {
            "mode": "compare",
            "model_a_id": "318878b7-c6a6-4c98-b228-b36ae505250c",
            "model_b_id": "864608e8-c05d-4ad0-bf46-ecc00b2045b6"
        }

        with self.client.post(
            "/sessions/",
            data=json.dumps(session_payload),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
            catch_response=True,
        ) as session_response:

            if session_response.status_code in [200, 201]:
                try:
                    session_data = session_response.json()

                    session_id = session_data.get("id")

                    # Extract model information (ID and NAME)
                    model_a_data = session_data.get("model_a", {})
                    model_b_data = session_data.get("model_b", {})

                    model_a_id = model_a_data.get("id")
                    model_b_id = model_b_data.get("id")
                    model_a_name = model_a_data.get("display_name", "Unknown")
                    model_b_name = model_b_data.get("display_name", "Unknown")

                    # Also get provider info if available
                    model_a_provider = model_a_data.get("provider", "")
                    model_b_provider = model_b_data.get("provider", "")

                    # Create full model identifier
                    model_a_full = f"{model_a_provider}:{model_a_name}" if model_a_provider else model_a_name
                    model_b_full = f"{model_b_provider}:{model_b_name}" if model_b_provider else model_b_name

                    # Validate essential fields
                    if not session_id:
                        session_response.failure("No session ID in response")
                        return
                    if not model_a_id or not model_b_id:
                        session_response.failure("Missing model IDs in session response")
                        return

                    print(f"Session {session_id}: {model_a_full} vs {model_b_full}")

                    # Step 2: Generate dynamic messages payload
                    user_msg_id = str(uuid.uuid4())
                    assistant_a_id = str(uuid.uuid4())
                    assistant_b_id = str(uuid.uuid4())
                    user_message = random.choice([
                        "Explain how photosynthesis works in simple terms",
                        "What causes lightning during a thunderstorm",
                        "Compare the Roman Empire and the Han Dynasty",
                        "Describe the process of making glass",
                        "Why is the sky blue during the day but red during sunset",
                        "How do airplanes stay in the air",
                        "What is the difference between RAM and ROM",
                        "How does a nuclear power plant generate electricity",
                        "Explain the difference between viruses and bacteria",
                        "Hey, how's your day going",
                        "Tell me a joke about programmers",
                        "What's your opinion on AI in education",
                    ])

                    message_payload = {
                        "session_id": session_id,
                        "messages": [
                            {
                                "id": user_msg_id,
                                "role": "user",
                                "content": user_message,
                                "parent_message_ids": [],
                                "status": "pending"
                            },
                            {
                                "id": assistant_a_id,
                                "role": "assistant",
                                "content": "",
                                "parent_message_ids": [user_msg_id],
                                "modelId": model_a_id,
                                "status": "pending",
                                "participant": "a"
                            },
                            {
                                "id": assistant_b_id,
                                "role": "assistant",
                                "content": "",
                                "parent_message_ids": [user_msg_id],
                                "modelId": model_b_id,
                                "status": "pending",
                                "participant": "b"
                            }
                        ]
                    }

                    # Step 3: Send message stream request with model tracking
                    with self.client.post(
                        "/messages/stream/",
                        data=json.dumps(message_payload),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
                        catch_response=True,
                        stream=True,
                        name=f"/messages/stream/ [{model_a_full} vs {model_b_full}]"  # Custom name with models
                    ) as message_response:

                        stream_failed = message_response.status_code not in [200, 201]

                        # Track model usage and failures
                        track_model_usage(
                            model_a_full,
                            model_b_full,
                            model_a_id,
                            model_b_id,
                            failed=stream_failed
                        )

                        if stream_failed:
                            # Enhanced failure message with model info
                            failure_msg = (
                                f"Stream failed ({message_response.status_code}) | "
                                f"Models: {model_a_full} vs {model_b_full} | "
                                f"Session: {session_id}"
                            )
                            message_response.failure(failure_msg)
                            print(f"❌ {failure_msg}")

                            # Try to get error details from response
                            try:
                                error_text = message_response.text[:200] if message_response.text else "No error text"
                                print(f"   Error details: {error_text}")
                            except:
                                pass
                        else:
                            print(f"✓ Stream success: {model_a_full} vs {model_b_full}")

                except Exception as e:
                    session_response.failure(f"Error parsing response: {e}")
                    print(f"Exception: {e}")
            else:
                session_response.failure(f"Session creation failed: {session_response.status_code}")
