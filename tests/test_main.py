"""Unit tests for the main CLI entry point."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from main import main


def _write_assignments(path: str, data: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(data, f)


class TestMainDryRun:
    def test_dry_run_prints_upcoming(self, capsys):
        data = [
            {
                "title": "Essay",
                "due_date": "2099-04-20T17:00:00+00:00",
                "course": "ENG 201",
                "description": "",
                "reminder_minutes": [60, 1440],
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name

        try:
            rc = main(["--assignments", tmp_path, "--dry-run"])
            captured = capsys.readouterr()
            assert rc == 0
            assert "Essay" in captured.out
            assert "upcoming" in captured.out
        finally:
            os.unlink(tmp_path)

    def test_dry_run_marks_past_due(self, capsys):
        data = [
            {
                "title": "Old Essay",
                "due_date": "2000-01-01T00:00:00+00:00",
                "course": "ENG 101",
                "description": "",
                "reminder_minutes": [60],
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name

        try:
            rc = main(["--assignments", tmp_path, "--dry-run"])
            captured = capsys.readouterr()
            assert rc == 0
            assert "PAST DUE" in captured.out
        finally:
            os.unlink(tmp_path)

    def test_missing_file_exits_zero(self, capsys):
        rc = main(["--assignments", "/tmp/no_such_file_xyz.json", "--dry-run"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "No assignments found" in captured.out


class TestMainSync:
    def test_sync_calls_calendar_and_saves(self, capsys):
        data = [
            {
                "title": "Lab",
                "due_date": "2099-04-15T23:59:00+00:00",
                "course": "CHEM 101",
                "description": "",
                "reminder_minutes": [60, 1440],
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name

        try:
            with patch("main.sync_assignments") as mock_sync, patch(
                "main.save_assignments"
            ) as mock_save:
                from src.assignment import load_assignments

                loaded = load_assignments(tmp_path)
                mock_sync.return_value = loaded

                rc = main(["--assignments", tmp_path])
                assert rc == 0
                mock_sync.assert_called_once()
                mock_save.assert_called_once()
        finally:
            os.unlink(tmp_path)
