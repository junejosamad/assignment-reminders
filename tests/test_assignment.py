"""Unit tests for the Assignment data model."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.assignment import Assignment, load_assignments, save_assignments


class TestAssignmentInit:
    def test_string_due_date_parsed(self):
        a = Assignment(title="Test", due_date="2026-04-15T23:59:00+00:00")
        assert isinstance(a.due_date, datetime)
        assert a.due_date.tzinfo is not None

    def test_naive_datetime_gets_utc(self):
        naive = datetime(2026, 4, 15, 23, 59)
        a = Assignment(title="Test", due_date=naive)
        assert a.due_date.tzinfo == timezone.utc

    def test_aware_datetime_preserved(self):
        aware = datetime(2026, 4, 15, 23, 59, tzinfo=timezone.utc)
        a = Assignment(title="Test", due_date=aware)
        assert a.due_date == aware

    def test_defaults(self):
        a = Assignment(title="Test", due_date="2026-04-15T23:59:00+00:00")
        assert a.course == ""
        assert a.description == ""
        assert a.reminder_minutes == [60, 1440]
        assert a.calendar_event_id is None


class TestIsPastDue:
    def test_future_assignment_is_not_past_due(self):
        a = Assignment(title="Future", due_date="2099-01-01T00:00:00+00:00")
        assert not a.is_past_due

    def test_past_assignment_is_past_due(self):
        a = Assignment(title="Past", due_date="2000-01-01T00:00:00+00:00")
        assert a.is_past_due


class TestToDict:
    def test_round_trip(self):
        a = Assignment(
            title="Essay",
            due_date="2026-04-20T17:00:00+00:00",
            course="ENG 201",
            description="MLA formatting",
            reminder_minutes=[120, 1440],
            calendar_event_id="abc123",
        )
        d = a.to_dict()
        assert d["title"] == "Essay"
        assert d["course"] == "ENG 201"
        assert d["calendar_event_id"] == "abc123"

    def test_no_event_id_key_when_none(self):
        a = Assignment(title="Test", due_date="2026-04-15T23:59:00+00:00")
        d = a.to_dict()
        assert "calendar_event_id" not in d

    def test_from_dict_round_trip(self):
        original = Assignment(
            title="Lab Report",
            due_date="2026-04-15T23:59:00+00:00",
            course="CHEM 101",
            reminder_minutes=[60, 1440],
        )
        restored = Assignment.from_dict(original.to_dict())
        assert restored.title == original.title
        assert restored.course == original.course
        assert restored.reminder_minutes == original.reminder_minutes


class TestLoadSaveAssignments:
    def test_load_missing_file_returns_empty(self):
        result = load_assignments("/tmp/nonexistent_assignments_xyz.json")
        assert result == []

    def test_save_and_load_round_trip(self):
        assignments = [
            Assignment(
                title="Test Assignment",
                due_date="2026-04-15T23:59:00+00:00",
                course="CS 101",
            )
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            save_assignments(assignments, tmp_path)
            loaded = load_assignments(tmp_path)
            assert len(loaded) == 1
            assert loaded[0].title == "Test Assignment"
            assert loaded[0].course == "CS 101"
        finally:
            os.unlink(tmp_path)

    def test_save_preserves_event_id(self):
        assignments = [
            Assignment(
                title="With Event",
                due_date="2026-04-15T23:59:00+00:00",
                calendar_event_id="evt_001",
            )
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            save_assignments(assignments, tmp_path)
            with open(tmp_path) as f:
                data = json.load(f)
            assert data[0]["calendar_event_id"] == "evt_001"
        finally:
            os.unlink(tmp_path)
