from locust import HttpUser, task, between
import random

class ChatArenaUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://localhost:8000"
    
    def on_start(self):
        '''Login if needed (for authenticated endpoints)'''
        pass
    
    @task(5)
    def list_models(self):
        '''WSGI: List AI models'''
        self.client.get("/api/models/")
    
    @task(3)
    def get_leaderboard(self):
        '''WSGI: Get leaderboard'''
        arena_types = ['LLM', 'TTS', 'ASR']
        arena_type = random.choice(arena_types)
        self.client.get(f"/api/leaderboard/{arena_type}/")
    
    @task(2)
    def admin_health(self):
        '''WSGI: Health check'''
        self.client.get("/admin/login/")
    
    @task(1)
    def list_messages(self):
        '''Future ASGI: List messages (currently WSGI)'''
        # This will become streaming endpoint
        with self.client.get("/api/messages/", catch_response=True) as response:
            if response.status_code == 401:
                # Expected - needs auth
                response.success()
    
    @task(1)
    def list_sessions(self):
        '''WSGI: List sessions'''
        with self.client.get("/api/sessions/", catch_response=True) as response:
            if response.status_code == 401:
                # Expected - needs auth
                response.success()
