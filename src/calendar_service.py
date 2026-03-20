"""Google Calendar service: authentication and event management."""

from __future__ import annotations

import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.assignment import Assignment
from src.config import CALENDAR_ID, CREDENTIALS_FILE, SCOPES, TOKEN_FILE


def get_credentials() -> Credentials:
    """Return valid Google OAuth2 credentials, refreshing or re-authorising as needed.

    On the first run an interactive browser-based OAuth2 flow is started.
    Subsequent runs use the cached token in :data:`~src.config.TOKEN_FILE`.

    Returns:
        A valid :class:`google.oauth2.credentials.Credentials` instance.

    Raises:
        FileNotFoundError: If ``credentials.json`` does not exist.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"OAuth2 credentials file not found: {CREDENTIALS_FILE}\n"
            "Download it from https://console.cloud.google.com/ and save it as "
            "'credentials.json' in the project root."
        )

    creds: Optional[Credentials] = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def build_service(credentials: Optional[Credentials] = None):
    """Build and return a Google Calendar API service resource.

    Args:
        credentials: Pre-built credentials.  If *None*, :func:`get_credentials`
            is called automatically.

    Returns:
        A Google Calendar API ``Resource`` object.
    """
    if credentials is None:
        credentials = get_credentials()
    return build("calendar", "v3", credentials=credentials)


def _build_event_body(assignment: Assignment) -> dict:
    """Construct the Google Calendar event payload for an assignment.

    Args:
        assignment: The assignment to convert.

    Returns:
        A dict suitable for ``events.insert`` / ``events.update``.
    """
    summary = assignment.title
    if assignment.course:
        summary = f"[{assignment.course}] {assignment.title}"

    due_iso = assignment.due_date.isoformat()

    reminders = [
        {"method": "email", "minutes": m} for m in assignment.reminder_minutes
    ] + [{"method": "popup", "minutes": m} for m in assignment.reminder_minutes]

    return {
        "summary": summary,
        "description": assignment.description,
        "start": {"dateTime": due_iso},
        "end": {"dateTime": due_iso},
        "reminders": {
            "useDefault": False,
            "overrides": reminders,
        },
    }


def create_event(assignment: Assignment, service=None) -> str:
    """Create a Google Calendar event for *assignment*.

    Args:
        assignment: The assignment to schedule.
        service: Optional pre-built Calendar API service (useful in tests).

    Returns:
        The Google Calendar event ID of the newly created event.

    Raises:
        googleapiclient.errors.HttpError: On API errors.
    """
    if service is None:
        service = build_service()

    event_body = _build_event_body(assignment)
    try:
        event = (
            service.events()
            .insert(calendarId=CALENDAR_ID, body=event_body)
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Failed to create event for '{assignment.title}': {exc}") from exc

    return event["id"]


def update_event(assignment: Assignment, service=None) -> None:
    """Update an existing Google Calendar event for *assignment*.

    Args:
        assignment: The assignment whose ``calendar_event_id`` points to the
            event to update.
        service: Optional pre-built Calendar API service.

    Raises:
        ValueError: If *assignment* has no ``calendar_event_id``.
        googleapiclient.errors.HttpError: On API errors.
    """
    if not assignment.calendar_event_id:
        raise ValueError(
            f"Assignment '{assignment.title}' has no calendar_event_id to update."
        )
    if service is None:
        service = build_service()

    event_body = _build_event_body(assignment)
    try:
        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=assignment.calendar_event_id,
            body=event_body,
        ).execute()
    except HttpError as exc:
        raise RuntimeError(
            f"Failed to update event '{assignment.calendar_event_id}': {exc}"
        ) from exc


def delete_event(event_id: str, service=None) -> None:
    """Delete a Google Calendar event by its ID.

    Args:
        event_id: The Google Calendar event ID to delete.
        service: Optional pre-built Calendar API service.

    Raises:
        googleapiclient.errors.HttpError: On API errors.
    """
    if service is None:
        service = build_service()
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except HttpError as exc:
        raise RuntimeError(f"Failed to delete event '{event_id}': {exc}") from exc


def sync_assignments(assignments: list[Assignment], service=None) -> list[Assignment]:
    """Synchronise a list of assignments to Google Calendar.

    * Assignments **without** a ``calendar_event_id`` are created.
    * Assignments **with** an existing ``calendar_event_id`` are updated.
    * Past-due assignments are skipped with a warning printed to stdout.

    Args:
        assignments: List of :class:`~src.assignment.Assignment` objects.
        service: Optional pre-built Calendar API service.

    Returns:
        The same list, with ``calendar_event_id`` populated for new events.
    """
    if service is None:
        service = build_service()

    for assignment in assignments:
        if assignment.is_past_due:
            print(f"  [skip]   '{assignment.title}' is past due – skipping.")
            continue

        if assignment.calendar_event_id:
            update_event(assignment, service=service)
            print(f"  [update] '{assignment.title}' updated (id={assignment.calendar_event_id}).")
        else:
            event_id = create_event(assignment, service=service)
            assignment.calendar_event_id = event_id
            print(f"  [create] '{assignment.title}' created (id={event_id}).")

    return assignments
