"""Unit tests for the Google Calendar service module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.assignment import Assignment
from src.calendar_service import (
    _build_event_body,
    create_event,
    delete_event,
    sync_assignments,
    update_event,
)


def _future_assignment(**kwargs) -> Assignment:
    defaults = dict(
        title="Test Assignment",
        due_date="2099-01-01T00:00:00+00:00",
        course="CS 101",
        description="Do stuff",
        reminder_minutes=[60, 1440],
    )
    defaults.update(kwargs)
    return Assignment(**defaults)


def _past_assignment(**kwargs) -> Assignment:
    defaults = dict(
        title="Old Assignment",
        due_date="2000-01-01T00:00:00+00:00",
        course="HIST 101",
    )
    defaults.update(kwargs)
    return Assignment(**defaults)


class TestBuildEventBody:
    def test_summary_includes_course(self):
        a = _future_assignment(title="Essay", course="ENG 201")
        body = _build_event_body(a)
        assert body["summary"] == "[ENG 201] Essay"

    def test_summary_no_course(self):
        a = _future_assignment(title="Essay", course="")
        body = _build_event_body(a)
        assert body["summary"] == "Essay"

    def test_description_included(self):
        a = _future_assignment(description="Do everything.")
        body = _build_event_body(a)
        assert body["description"] == "Do everything."

    def test_reminders_contain_email_and_popup(self):
        a = _future_assignment(reminder_minutes=[60, 1440])
        body = _build_event_body(a)
        overrides = body["reminders"]["overrides"]
        methods = [o["method"] for o in overrides]
        assert "email" in methods
        assert "popup" in methods

    def test_reminders_use_default_false(self):
        a = _future_assignment()
        body = _build_event_body(a)
        assert body["reminders"]["useDefault"] is False

    def test_start_and_end_are_same(self):
        a = _future_assignment()
        body = _build_event_body(a)
        assert body["start"]["dateTime"] == body["end"]["dateTime"]


class TestCreateEvent:
    def test_returns_event_id(self):
        mock_service = MagicMock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "event_abc"
        }

        a = _future_assignment()
        event_id = create_event(a, service=mock_service)
        assert event_id == "event_abc"

    def test_insert_called_with_correct_calendar(self):
        mock_service = MagicMock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "event_abc"
        }

        a = _future_assignment()
        create_event(a, service=mock_service)

        mock_service.events.return_value.insert.assert_called_once()
        call_kwargs = mock_service.events.return_value.insert.call_args[1]
        assert "calendarId" in call_kwargs


class TestUpdateEvent:
    def test_update_raises_if_no_event_id(self):
        a = _future_assignment()
        with pytest.raises(ValueError, match="no calendar_event_id"):
            update_event(a, service=MagicMock())

    def test_update_calls_api(self):
        mock_service = MagicMock()
        mock_service.events.return_value.update.return_value.execute.return_value = {}

        a = _future_assignment(calendar_event_id="evt_001")
        update_event(a, service=mock_service)

        mock_service.events.return_value.update.assert_called_once()


class TestDeleteEvent:
    def test_delete_calls_api(self):
        mock_service = MagicMock()
        mock_service.events.return_value.delete.return_value.execute.return_value = None

        delete_event("evt_001", service=mock_service)

        mock_service.events.return_value.delete.assert_called_once()


class TestSyncAssignments:
    def test_creates_new_events(self):
        mock_service = MagicMock()
        mock_service.events().insert().execute.return_value = {"id": "new_evt"}

        a = _future_assignment()
        result = sync_assignments([a], service=mock_service)

        assert result[0].calendar_event_id == "new_evt"

    def test_updates_existing_events(self):
        mock_service = MagicMock()
        mock_service.events.return_value.update.return_value.execute.return_value = {}

        a = _future_assignment(calendar_event_id="existing_evt")
        sync_assignments([a], service=mock_service)

        mock_service.events.return_value.update.assert_called_once()
        mock_service.events.return_value.insert.assert_not_called()

    def test_skips_past_due_assignments(self):
        mock_service = MagicMock()

        past = _past_assignment()
        result = sync_assignments([past], service=mock_service)

        mock_service.events().insert.assert_not_called()
        mock_service.events().update.assert_not_called()
        assert result[0].calendar_event_id is None

    def test_mixed_list(self):
        mock_service = MagicMock()
        mock_service.events().insert().execute.return_value = {"id": "new_evt"}

        future = _future_assignment()
        past = _past_assignment()

        result = sync_assignments([future, past], service=mock_service)

        assert result[0].calendar_event_id == "new_evt"
        assert result[1].calendar_event_id is None
