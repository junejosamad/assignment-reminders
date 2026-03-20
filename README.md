# assignment-reminders

Automatically sync your assignment due dates to **Google Calendar** – so you never miss a deadline.

## Features

- Reads assignments from a local JSON file (`assignments.json`)
- Creates and updates Google Calendar events with configurable email **and** popup reminders
- Skips past-due assignments automatically
- Persists Google Calendar event IDs back to the JSON file so subsequent runs update existing events instead of duplicating them
- `--dry-run` mode to preview assignments without touching your calendar

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9+ | Tested on 3.9 – 3.12 |
| Google account | Any personal or Workspace account |
| Google Cloud project | Free tier is sufficient |

## Setup

### 1. Enable the Google Calendar API

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Navigate to **APIs & Services → Library** and enable the **Google Calendar API**.
4. Navigate to **APIs & Services → Credentials** and create an **OAuth 2.0 Client ID** (Desktop app type).
5. Download the credentials JSON and save it as **`credentials.json`** in the project root.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Populate your assignments

Edit `assignments.json` (an example file is included):

```json
[
  {
    "title": "Lab Report 1",
    "due_date": "2026-04-15T23:59:00+00:00",
    "course": "CHEM 101",
    "description": "Submit via the course portal.",
    "reminder_minutes": [60, 1440]
  }
]
```

| Field | Required | Description |
|---|---|---|
| `title` | ✅ | Assignment name |
| `due_date` | ✅ | ISO 8601 datetime (timezone-aware recommended) |
| `course` | | Course name – prepended to the calendar event title |
| `description` | | Free-text notes added to the calendar event body |
| `reminder_minutes` | | Minutes before due date to send reminders (default `[60, 1440]`) |

### 4. Run

```bash
# Preview assignments (no calendar changes)
python main.py --dry-run

# Sync to Google Calendar (opens a browser for OAuth on first run)
python main.py
```

On the first run a browser window opens for Google OAuth authorisation.  
A `token.json` file is saved locally for subsequent runs – **keep it private**.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_CREDENTIALS_FILE` | `credentials.json` | Path to the OAuth client-secrets file |
| `GOOGLE_TOKEN_FILE` | `token.json` | Path where the user token is cached |
| `ASSIGNMENTS_FILE` | `assignments.json` | Path to the assignments data file |
| `GOOGLE_CALENDAR_ID` | `primary` | Target calendar ID |

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
assignment-reminders/
├── main.py                  # CLI entry point
├── assignments.json         # Your assignments (edit this)
├── requirements.txt
├── src/
│   ├── assignment.py        # Assignment model + JSON load/save
│   ├── calendar_service.py  # Google Calendar API integration
│   └── config.py            # Paths and OAuth settings
└── tests/
    ├── test_assignment.py
    ├── test_calendar_service.py
    └── test_main.py
```
