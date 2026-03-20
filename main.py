#!/usr/bin/env python3
"""Assignment Reminders – main entry point.

Usage
-----
    python main.py [--assignments <path>] [--dry-run]

Options
-------
--assignments   Path to the assignments JSON file.
                Defaults to the value of the ``ASSIGNMENTS_FILE`` env var
                or ``assignments.json`` in the project root.
--dry-run       Print assignments without creating/updating calendar events.
"""

from __future__ import annotations

import argparse
import sys

from src.assignment import load_assignments, save_assignments
from src.calendar_service import sync_assignments
from src.config import ASSIGNMENTS_FILE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync assignment due dates to Google Calendar."
    )
    parser.add_argument(
        "--assignments",
        default=ASSIGNMENTS_FILE,
        help="Path to the assignments JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print assignments without contacting Google Calendar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    assignments = load_assignments(args.assignments)
    if not assignments:
        print(f"No assignments found in '{args.assignments}'. Exiting.")
        return 0

    print(f"Loaded {len(assignments)} assignment(s) from '{args.assignments}'.\n")

    if args.dry_run:
        for a in assignments:
            status = "PAST DUE" if a.is_past_due else "upcoming"
            print(f"  [{status}] {a.title} – due {a.due_date.strftime('%Y-%m-%d %H:%M %Z')}")
            if a.course:
                print(f"            Course: {a.course}")
        return 0

    updated = sync_assignments(assignments)
    save_assignments(updated, args.assignments)
    print(f"\nDone. '{args.assignments}' updated with calendar event IDs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
