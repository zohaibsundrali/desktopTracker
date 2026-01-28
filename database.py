# database.py
import json
import requests
from datetime import datetime

class SupabaseClient:
    def __init__(self, url, key):
        self.url = url
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
    def save_session(self, session_data):
        """Save tracking session to database"""
        endpoint = f"{self.url}/rest/v1/sessions"
        
        data = {
            "user_id": session_data.get("user_id"),
            "session_id": session_data.get("session_id"),
            "start_time": session_data.get("start_time"),
            "end_time": session_data.get("end_time"),
            "productivity_score": session_data.get("productivity_score"),
            "duration_minutes": session_data.get("duration_minutes"),
            "mouse_events": session_data.get("mouse_events"),
            "keyboard_events": session_data.get("keyboard_events"),
            "created_at": datetime.now().isoformat()
        }
        
        try:
            response = requests.post(endpoint, json=data, headers=self.headers)
            return response.status_code == 201
        except Exception as e:
            print(f"Database error: {e}")
            return False

# Mock database for testing
class MockDatabase:
    def save_session(self, session_data):
        print(f"💾 [MOCK] Would save session: {session_data['session_id']}")
        return True