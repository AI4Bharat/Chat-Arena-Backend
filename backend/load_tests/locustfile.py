from locust import HttpUser, task, between
import json
import uuid
import random

class ArenaUser(HttpUser):
    wait_time = between(1, 3)  # Simulate think time (1–3 sec gap)

    @task
    def create_session_and_stream(self):
        with self.client.post(
            "/auth/anonymous/",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as auth_response:
            if auth_response.status_code == 200:
                auth_data = auth_response.json()

                print("Starting create_session_and_stream task...")

                # Step 1: Create Session
                session_payload = {
                    "mode": "random",
                    "model_a_id": "",
                    "model_b_id": ""
                }
                print(f"Sending session creation request with payload: {session_payload}")

                with self.client.post(
                    "/sessions/",
                    data=json.dumps(session_payload),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {auth_data['tokens']['access']}"},
                    catch_response=True,
                ) as session_response:
                    print(f"Received session response: {session_response.status_code}")

                    if session_response.status_code == 200:
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
                            user_message = random.choice(["hi", "hello", "how are you?", "good morning", "hey there!"])

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
                                headers={"Content-Type": "application/json", "Authorization": f"Bearer {auth_data['tokens']['access']}"},
                                catch_response=True,
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


