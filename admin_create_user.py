"""
admin_create_user.py - ADMIN ONLY tool to provision employee accounts.

Run this on the ADMIN's machine only. It uses the Supabase *service_role* key
(full admin) to:
  1. create the user in Supabase Auth (password is hashed by Supabase), and
  2. create the matching `developers` profile row with id = the auth user id,

so that every data table (which stores user_id / developer_id = developers.id)
lines up with auth.uid() and RLS works.

NEVER ship this file, or the service_role key, inside the distributed .exe.

Usage:
    # set the service_role key just for this admin session (do NOT commit it)
    set SUPABASE_URL=https://isaccqqjobuwfeaxlrwc.supabase.co
    set SUPABASE_SERVICE_KEY=<your service_role key>

    python admin_create_user.py --email dev@company.com --password "S0mePass!" \
        --name "Dev Name" --company "Acme"
"""
import argparse
import os
import sys

from supabase import create_client


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a tracker employee account.")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--company", default="")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY (service_role) "
              "environment variables first.")
        return 1

    sb = create_client(url, service_key)

    # 1) Create the auth user (email pre-confirmed so they can log in at once).
    try:
        created = sb.auth.admin.create_user({
            "email": args.email,
            "password": args.password,
            "email_confirm": True,
            "user_metadata": {"name": args.name, "company": args.company},
        })
        user = getattr(created, "user", None) or created
        user_id = user.id if hasattr(user, "id") else user["id"]
    except Exception as e:
        print(f"ERROR creating auth user: {e}")
        return 1

    # 2) Create the matching profile row with the SAME id.
    try:
        sb.table("developers").upsert({
            "id": user_id,
            "email": args.email,
            "name": args.name,
            "company": args.company,
            "status": "active",
        }, on_conflict="id").execute()
    except Exception as e:
        print(f"WARNING: auth user created ({user_id}) but profile insert failed: {e}")
        print("Fix the developers row manually, then the account will work.")
        return 1

    print(f"OK: created {args.email}  (id={user_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
