# locustfile.py
from locust import HttpUser, task, between
from dotenv import load_dotenv
from pathlib import Path
import os


# Fetch credentials
EMAIL = os.getenv("EMAIL") 
PASSWORD = os.getenv("PASSWORD")


class ProjectUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def create_project(self):
        login_payload = {"email": EMAIL, "password": PASSWORD}
        login_headers = {"Content-Type": "application/json"}

        with self.client.post("/users/auth/jwt/create",
                              json=login_payload,
                              headers=login_headers,
                              catch_response=True) as login_resp:
            if login_resp.status_code == 200:
                access_token = login_resp.json().get("access")
                if access_token:
                    auth_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                    # Example POST to /projects/ with payload
                    project_payload = {
                        "name": "LoadTest project",
                        "description": "created by locust",
                    }
                    with self.client.post("/projects/", json=project_payload, headers=auth_headers, catch_response=True) as resp:
                        if resp.status_code in (200, 201):
                            resp.success()
                        else:
                            resp.failure(f"Project POST failed: {resp.status_code} | {resp.text}")
                else:
                    login_resp.failure("Login succeeded but no access token in response")
            else:
                login_resp.failure(f"Login failed: {login_resp.status_code} | {login_resp.text}")


### A simpler locustfile that only does GET API when env loading is not needed and no authentication is required:

# from locust import HttpUser, task, between

# class ProjectUser(HttpUser):
#     wait_time = between(1, 2)

#     @task
#     def get_projects(self):
#         self.client.get("/projects/")





### requires authentication (JWT or token)

# from locust import HttpUser, task, between

# class ProjectUser(HttpUser):
#     wait_time = between(1, 2)

#     # Use a valid JWT token from your Django app (copy from Postman or browser)
#     access_token = "YOUR_VALID_JWT_ACCESS_TOKEN"

#     @task
#     def get_projects(self):
#         headers = {
#             "Authorization": f"Bearer {self.access_token}",
#             "Content-Type": "application/json"
#         }
#         self.client.get("/projects/", headers=headers)


### If Api Requires Some Payload in GET Request

# from locust import HttpUser, task, between

# class ProjectUser(HttpUser):
#     wait_time = between(1, 2)

#     @task
#     def create_project(self):
#         payload = {
#             "name": "Test Project",
#             "description": "This is a load test project from Locust"
#         }
#         headers = {"Content-Type": "application/json"}

#         self.client.post("/projects/", json=payload, headers=headers)

