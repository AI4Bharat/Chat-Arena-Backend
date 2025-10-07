import os
import firebase_admin
from firebase_admin import credentials

def initialize_firebase():
    """
    Safely initialize Firebase Admin SDK once globally.
    This can be imported anywhere in your Django app.
    """
    if not firebase_admin._apps:
        firebase_key_path = os.getenv("FIREBASE_CREDENTIALS")

        if firebase_key_path and os.path.exists(firebase_key_path):
            cred = credentials.Certificate(firebase_key_path)
            firebase_admin.initialize_app(cred)
        else:
            # Optionally support credentials via JSON string (for Docker env var)
            firebase_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            if firebase_json:
                import json
                cred = credentials.Certificate(json.loads(firebase_json))
                firebase_admin.initialize_app(cred)
            else:
                raise RuntimeError("Firebase credentials not provided properly.")
