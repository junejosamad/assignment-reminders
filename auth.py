#!/usr/bin/env python3
"""
Bahria Assignment Tracker — auth.py
Run this ONCE on your LOCAL machine (not the server).
It opens a browser for Google authorization and saves token.json.
Then upload token.json to your hosting server.

Usage:
  pip install google-auth-oauthlib google-api-python-client
  python auth.py
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE       = "token.json"

def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(
            "\n❌  credentials.json not found!\n\n"
            "Steps to get it:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create a project (or use an existing one)\n"
            "  3. Enable 'Google Calendar API'\n"
            "     APIs & Services → Enable APIs & Services → search 'Calendar'\n"
            "  4. APIs & Services → Credentials → Create Credentials\n"
            "     → OAuth 2.0 Client ID → Desktop app\n"
            "  5. Download JSON → rename to credentials.json\n"
            "  6. Place credentials.json in this folder and re-run auth.py\n"
        )
        return

    print("Opening browser for Google authorization...")
    print("(If browser doesn't open, copy the URL printed below.)\n")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅  token.json saved successfully!")
    print(f"\nNext step:")
    print(f"  Upload '{TOKEN_FILE}' to your hosting server in the same folder as sync.py")
    print(f"  The token auto-refreshes, so you only need to do this once.\n")

if __name__ == "__main__":
    main()
