from locust import HttpUser, task, between
import json
import uuid
import random

class ArenaUser(HttpUser):
    wait_time = between(1, 3)  # Simulate think time (1–3 sec gap)

    def on_start(self):
        """
        Called once when a simulated user starts.
        Authenticate here and reuse the token for all subsequent requests.
        This is more realistic - users don't re-authenticate on every request!
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
            print(f"User authenticated successfully - token will be reused")
        else:
            print(f"Authentication failed: {auth_response.status_code}")
            self.access_token = None

    @task
    def create_session_and_stream(self):
        """
        Now this task just creates sessions and streams - no re-authentication!
        """
        if not self.access_token:
            print("No access token - skipping task")
            return

        print("Starting create_session_and_stream task...")

        # Step 1: Create Session
        session_payload = {
            "mode": "random",
            "model_a_id": None,
            "model_b_id": None
        }
        print(f"Sending session creation request with payload: {session_payload}")

        with self.client.post(
            "/sessions/",
            data=json.dumps(session_payload),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
            catch_response=True,
        ) as session_response:
            print(f"Received session response: {session_response.status_code}")

            if session_response.status_code in [200, 201]:
                try:
                    session_data = session_response.json()
                    print(f"Session response JSON: {json.dumps(session_data, indent=2)}")

                    session_id = session_data.get("id")
                    model_a_id = session_data.get("model_a", {}).get("id")
                    model_b_id = session_data.get("model_b", {}).get("id")

                    # Validate essential fields
                    if not session_id:
                        session_response.failure("No session ID in response")
                        print("Failed: No session ID in response")
                        return
                    if not model_a_id or not model_b_id:
                        session_response.failure("Missing model IDs in session response")
                        print(f"Failed: model_a_id={model_a_id}, model_b_id={model_b_id}")
                        return

                    print(f"Session created successfully with ID: {session_id}")
                    print(f"Using model_a_id: {model_a_id}")
                    print(f"Using model_b_id: {model_b_id}")

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
        "List the seven continents and their largest cities",
        "How does a nuclear power plant generate electricity",
        "Explain the difference between viruses and bacteria",
        "Hey, how's your day going",
        "Can you tell me a fun fact",
        "What's the best movie you've seen recently",
        "Tell me a joke about programmers",
        "How do you usually spend your weekends",
        "What would you do if you could travel anywhere",
        "I'm bored. Can we play a word game",
        "What's your opinion on AI in education",
        "What's the best advice you've ever heard",
        "Do you believe in luck",
        "Solve: (23 × 17) + (45 ÷ 5)",
        "What is the derivative of sin(x) * e^x",
        "How many permutations of the word 'APPLE' exist",
        "If a train travels 90 km in 1.5 hours, what's its speed",
        "Find the next number: 2, 4, 8, 16, __",
        "Simplify: (x² - 4)/(x - 2)",
        "Calculate the probability of getting a head 3 times in a row",
        "How many seconds are there in 3 days",
        "What is the sum of all even numbers from 1 to 100",
        "Explain the difference between mean, median, and mode",
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

                    print(f"Sending message payload:\n{json.dumps(message_payload, indent=2)}")

                    # Step 3: Send message stream request
                    with self.client.post(
                        "/messages/stream/",
                        data=json.dumps(message_payload),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
                        catch_response=True,
                        stream=True,  # Important for SSE
                    ) as message_response:
                        print(f"Received message stream response: {message_response.status_code}")
                        if message_response.status_code not in [200, 201]:
                            message_response.failure(
                                f"Stream failed ({message_response.status_code})"
                            )
                            print(f"Stream failed with status: {message_response.status_code}")
                        else:
                            print("Message streamed successfully!")

                except Exception as e:
                    session_response.failure(f"Error parsing response: {e}")
                    print(f"Exception occurred while parsing session response: {e}")
            else:
                session_response.failure(f"Session creation failed: {session_response.status_code}")
                print(f"Session creation failed with status: {session_response.status_code}")
