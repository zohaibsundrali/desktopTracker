# check_database.py
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

try:
    supabase = create_client(url, key)
    print("✅ Connected to Supabase")
    
    # Check developers table
    try:
        devs = supabase.table("developers").select("*").limit(1).execute()
        print(f"✅ Developers table: {len(devs.data)} records")
    except Exception as e:
        print(f"❌ Developers table error: {e}")
    
    # Check productivity_sessions table
    try:
        sessions = supabase.table("productivity_sessions").select("*").limit(1).execute()
        print(f"✅ Productivity sessions table: {len(sessions.data)} records")
    except Exception as e:
        print(f"❌ Productivity sessions error: {e}")
    
    # Check app_usage table
    try:
        app_usage = supabase.table("app_usage").select("*").limit(1).execute()
        print(f"✅ App usage table: {len(app_usage.data)} records")
    except Exception as e:
        print(f"❌ App usage error: {e}")
    
    # List all tables (if possible)
    print("\n📋 Database check complete!")
    
except Exception as e:
    print(f"❌ Connection error: {e}")