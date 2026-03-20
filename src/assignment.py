"""Assignment data model and JSON loader."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Assignment:
    """Represents a single assignment with its due date and metadata."""

    title: str
    due_date: datetime
    course: str = ""
    description: str = ""
    reminder_minutes: list[int] = field(default_factory=lambda: [60, 1440])
    calendar_event_id: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.due_date, str):
            from dateutil import parser as dateutil_parser

            parsed = dateutil_parser.parse(self.due_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            self.due_date = parsed
        elif self.due_date.tzinfo is None:
            self.due_date = self.due_date.replace(tzinfo=timezone.utc)

    @property
    def is_past_due(self) -> bool:
        """Return True if the assignment due date is in the past."""
        return self.due_date < datetime.now(tz=timezone.utc)

    def to_dict(self) -> dict:
        """Serialise to a plain dict (suitable for JSON round-trip)."""
        d: dict = {
            "title": self.title,
            "due_date": self.due_date.isoformat(),
            "course": self.course,
            "description": self.description,
            "reminder_minutes": self.reminder_minutes,
        }
        if self.calendar_event_id:
            d["calendar_event_id"] = self.calendar_event_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Assignment":
        """Create an Assignment from a plain dict."""
        return cls(
            title=data["title"],
            due_date=data["due_date"],
            course=data.get("course", ""),
            description=data.get("description", ""),
            reminder_minutes=data.get("reminder_minutes", [60, 1440]),
            calendar_event_id=data.get("calendar_event_id"),
        )


def load_assignments(path: str) -> list[Assignment]:
    """Load assignments from a JSON file.

    Args:
        path: Absolute or relative path to the JSON assignments file.

    Returns:
        A list of :class:`Assignment` objects.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [Assignment.from_dict(item) for item in data]


def save_assignments(assignments: list[Assignment], path: str) -> None:
    """Persist assignments (including any calendar_event_id values) to JSON.

    Args:
        assignments: List of :class:`Assignment` objects to serialise.
        path: Destination file path.
    """
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([a.to_dict() for a in assignments], fh, indent=2)
