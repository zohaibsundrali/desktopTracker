# test_supabase.py
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Test connection
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print(f"URL: {url}")
print(f"Key present: {bool(key)}")

try:
    supabase = create_client(url, key)
    print("✅ Supabase client created")
    
    # Test query
    response = supabase.table("developers").select("*").limit(1).execute()
    print(f"✅ Query successful, found {len(response.data)} users")
    
except Exception as e:
    print(f"❌ Supabase error: {e}")