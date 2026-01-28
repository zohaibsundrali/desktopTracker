# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "your_supabase_url")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your_supabase_key")
    
    # App Configuration
    APP_NAME = "Developer Activity And  Productivity Tracking"
    VERSION = "1.0.0"
    
    # Paths
    DATA_DIR = "user_data"
    SCREENSHOT_DIR = "screenshots"
    
config = Config()