# auth_manager.py - CLEAN SIMPLE VERSION
from datetime import datetime, timedelta
from supabase import create_client
import jwt
from config import config
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class User:
    id: str
    email: str
    name: str
    company: str
    status: str
    created_at: str
    role: str = "developer"  # Default value since no column in DB
    

class AuthManager:
    def __init__(self):
        self.supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
        self.current_user: Optional[User] = None
        self.token_secret = "your-secret-key-change-this"
        
    def register_user(self, email: str, password: str, name: str, 
                     company: str) -> Tuple[bool, str]:
        """
        Register new user
        Returns: (success, message)
        """
        try:
            # Check if email exists
            existing = self.supabase.table("developers")\
                .select("*")\
                .eq("email", email)\
                .execute()
            
            if existing.data:
                return False, "Email already registered"
            
            # Insert user
            user_data = {
                "email": email,
                "password": password,  # Plain text store
                "name": name,
                "company": company,
                "status": "active",
                "projects_count": 0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            
            result = self.supabase.table("developers")\
                .insert(user_data)\
                .execute()
            
            if result.data:
                return True, "Registration successful"
            else:
                return False, "Registration failed"
                
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def login(self, email: str, password: str) -> Tuple[bool, str, Optional[User]]:
        """
        Login user
        Returns: (success, message, user_object)
        """
        try:
            # Get user from Supabase
            result = self.supabase.table("developers")\
                .select("*")\
                .eq("email", email)\
                .execute()
            
            if not result.data:
                return False, "Invalid email or password", None
            
            user_data = result.data[0]
            
            # Password comparison
            stored_password = user_data.get("password", "")
            
            if stored_password != password:
                return False, "Invalid email or password", None
            
            # Check status
            if user_data.get("status") != "active":
                return False, "Account is not active", None
            
            # Create user object
            user = User(
                id=str(user_data["id"]),
                email=user_data["email"],
                name=user_data.get("name", ""),
                company=user_data.get("company", ""),
                status=user_data.get("status", "active"),
                created_at=user_data.get("created_at", ""),
                role="developer"
            )
            
            self.current_user = user
            
            return True, "Login successful", user
            
        except Exception as e:
            return False, f"Error: {str(e)}", None
    
    def generate_token(self, user_id: str) -> str:
        """Generate JWT token"""
        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(hours=24)
        }
        return jwt.encode(payload, self.token_secret, algorithm="HS256")
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify JWT token and return user_id"""
        try:
            payload = jwt.decode(token, self.token_secret, algorithms=["HS256"])
            return payload.get("user_id")
        except:
            return None
    
    def logout(self):
        """Logout current user"""
        self.current_user = None
    
    def get_current_user(self) -> Optional[User]:
        """Get currently logged in user"""
        return self.current_user

# Quick test if run directly
if __name__ == "__main__":
    print("🔐 Auth Manager - Ready")
    print("Use in your application with:")
    print("1. from auth_manager import AuthManager, User")
    print("2. auth = AuthManager()")
    print("3. success, message, user = auth.login(email, password)")