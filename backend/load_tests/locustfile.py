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
            if auth_response.status_code in [200, 201]:
                auth_data = auth_response.json()

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
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {auth_data['tokens']['access']}"},
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
    "Hey, how’s your day going",
    "Can you tell me a fun fact",
    "What’s the best movie you’ve seen recently",
    "Tell me a joke about programmers",
    "How do you usually spend your weekends",
    "What would you do if you could travel anywhere",
    "I’m bored. Can we play a word game",
    "What’s your opinion on AI in education",
    "What’s the best advice you’ve ever heard",
    "Do you believe in luck",
    "Solve: (23 × 17) + (45 ÷ 5)",
    "What is the derivative of sin(x) * e^x",
    "How many permutations of the word 'APPLE' exist",
    "If a train travels 90 km in 1.5 hours, what’s its speed",
    "Find the next number: 2, 4, 8, 16, __",
    "Simplify: (x² - 4)/(x - 2)",
    "Calculate the probability of getting a head 3 times in a row",
    "How many seconds are there in 3 days",
    "What is the sum of all even numbers from 1 to 100",
    "Explain the difference between mean, median, and mode",
    "Summarize this paragraph: 'Artificial intelligence is rapidly evolving…'",
    "Summarize the main points of climate change debates",
    "Give a 3-sentence summary of the plot of Inception",
    "Condense this paragraph about World War II into one line",
    "Explain the key idea of Newton’s laws briefly",
    "Summarize the difference between capitalism and socialism",
    "Shorten this text: 'Electric cars are becoming popular…'",
    "What’s the summary of the article about deep learning advancements",
    "Explain blockchain in one short paragraph",
    "Give a summary of Hamlet",
    "Write a short story about a robot discovering emotions",
    "Describe a sunset on Mars in poetic form",
    "Write a haiku about rain",
    "Create a dialogue between a scientist and an alien",
    "Write a motivational quote for entrepreneurs",
    "Compose a limerick about coding",
    "Imagine if humans could breathe underwater — describe that world",
    "Write a futuristic story about AI ruling the world",
    "Create a short horror story set in an abandoned school",
    "Describe an ancient library filled with secrets",
    "Explain how to bake chocolate chip cookies step by step",
    "Describe the process of setting up a GitHub repo",
    "Give a step-by-step guide to changing a car tire",
    "Teach a beginner how to play chess",
    "Explain how to start a Python virtual environment",
    "Write steps to secure a Linux server",
    "How do you clean a DSLR camera lens",
    "Explain how to make a paper airplane that flies far",
    "How to install and use Docker on Ubuntu",
    "Write instructions to make a French press coffee",
    "If all cats are animals and some animals are dogs, can all dogs be cats",
    "Two people start at opposite ends of a 10 km road and walk toward each other at 2 km/h and 3 km/h. When do they meet",
    "You have 3 switches and a bulb in another room — how to find which switch controls the bulb",
    "How can you measure exactly 4 liters using only a 3L and 5L container",
    "A farmer has 17 sheep, all but 9 die. How many are left",
    "Which weighs more: a pound of feathers or a pound of iron",
    "A man looks at a photo of someone. He says, 'Brothers and sisters, I have none, but that man’s father is my father’s son.' Who’s in the photo",
    "Why is the letter 'e' most common in English",
    "What’s the next term in this pattern: AB, ABCD, ABCDEF, …",
    "Explain how you’d convince someone the Earth is round",
    "List the top 10 most populous countries in 2025",
    "What are the chemical properties of water",
    "Explain the structure of the human heart",
    "List all planets in order from the Sun",
    "What are the different types of renewable energy",
    "Who invented the telephone",
    "Give a timeline of major AI milestones",
    "List five major programming paradigms",
    "Describe the GDP ranking of the top 5 countries",
    "What are the major layers of the Earth",
    "Explain how a large language model processes a question",
    "What is tokenization in LLMs",
    "How does transformer architecture enable attention",
    "Compare GPT-4 and GPT-3.5 in terms of latency",
    "What affects inference speed in LLMs",
    "Why does response time vary with prompt length",
    "Explain the difference between context length and token count",
    "How can temperature parameter affect creativity",
    "How does caching improve LLM throughput",
    "What is prompt optimization and why is it important",
    "Generate a 200-word lorem ipsum text",
    "Explain quantum computing in detail",
    "Translate this sentence into 10 languages: 'AI will change the world.'",
    "Write a 1-paragraph code documentation for a Python API",
    "Summarize the contents of the U.S. Constitution",
    "List 100 programming languages alphabetically",
    "Explain in-depth how convolutional neural networks work",
    "Simulate a mock debate about renewable energy between two people",
    "Generate a long JSON example with 10 nested fields",
    "Write a structured outline for a 10-chapter science fiction novel"
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


