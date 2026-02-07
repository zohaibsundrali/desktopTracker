# main.py
import sys
import os
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Check if Supabase credentials are set
if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
    print("❌ ERROR: Supabase credentials not found!")
    print("Please create a .env file with:")
    print("SUPABASE_URL=your_supabase_url")
    print("SUPABASE_KEY=your_supabase_key")
    print("\nOr set them as environment variables.")
    sys.exit(1)

def main():
    """Main application entry point"""
    try:
        from gui_login import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        print("\nPlease install required packages:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()