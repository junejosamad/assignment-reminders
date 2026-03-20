"""Configuration and Google OAuth2 authentication helpers."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# File paths (can be overridden via environment variables)
# ---------------------------------------------------------------------------

#: Path to the OAuth2 client-secrets file downloaded from Google Cloud Console.
CREDENTIALS_FILE: str = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    str(Path(__file__).parent.parent / "credentials.json"),
)

#: Path where the user token is cached after the first OAuth2 flow.
TOKEN_FILE: str = os.environ.get(
    "GOOGLE_TOKEN_FILE",
    str(Path(__file__).parent.parent / "token.json"),
)

#: Path to the assignments JSON data file.
ASSIGNMENTS_FILE: str = os.environ.get(
    "ASSIGNMENTS_FILE",
    str(Path(__file__).parent.parent / "assignments.json"),
)

# ---------------------------------------------------------------------------
# Google Calendar API settings
# ---------------------------------------------------------------------------

#: OAuth2 scopes required by this application.
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar.events"]

#: Default Google Calendar to target.  "primary" refers to the user's default
#: calendar; set ``GOOGLE_CALENDAR_ID`` to use a different calendar.
CALENDAR_ID: str = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
