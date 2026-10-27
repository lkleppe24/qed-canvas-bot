"""Pure logic for spotting new submissions. No network, so it's easy to test."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SUBMITTED_STATES = {"submitted", "graded", "pending_review"}


@dataclass
class Submission:
    course_name: str
    assignment_name: str
    assignment_url: str
    submitted_at: str
    due_at: str | None
    attempt: int
    late: bool

    @property
    def is_resubmission(self) -> bool:
        return self.attempt > 1


def is_group_assignment(assignment: dict) -> bool:
    return assignment.get("group_category_id") is not None


def is_submitted(sub: dict | None) -> bool:
    return bool(sub) and bool(sub.get("submitted_at")) and (
        sub.get("workflow_state") in SUBMITTED_STATES
    )


def state_key(course_id, assignment_id) -> str:
    return f"{course_id}:{assignment_id}"


def find_new_submissions(
    course: dict,
    assignments: list[dict],
    state: dict[str, int],
    group_only: bool = True,
) -> list[Submission]:
    """Compare assignments against saved state; update state in place.

    state maps "course:assignment" -> last attempt number we've seen submitted.
    Returns submissions that are new (or new attempts) since last check.
    """
    found: list[Submission] = []
    for a in assignments:
        if group_only and not is_group_assignment(a):
            continue
        sub = a.get("submission")
        if not is_submitted(sub):
            continue
        key = state_key(course["id"], a["id"])
        attempt = int(sub.get("attempt") or 1)
        if state.get(key, 0) >= attempt:
            continue
        state[key] = attempt
        found.append(
            Submission(
                course_name=course.get("name") or course.get("course_code") or str(course["id"]),
                assignment_name=a.get("name", "Untitled assignment"),
                assignment_url=a.get("html_url", ""),
                submitted_at=sub["submitted_at"],
                due_at=a.get("due_at"),
                attempt=attempt,
                late=bool(sub.get("late")),
            )
        )
    return found


def pending_group_assignments(course: dict, assignments: list[dict]) -> list[dict]:
    """Group assignments with a future due date that nobody has submitted yet."""
    now = datetime.now(timezone.utc)
    out = []
    for a in assignments:
        if not is_group_assignment(a) or is_submitted(a.get("submission")):
            continue
        due = parse_time(a.get("due_at"))
        if due and due > now:
            out.append({"course": course.get("name", ""), "name": a.get("name", ""),
                        "due": due, "url": a.get("html_url", "")})
    return out


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class StateStore:
    """Tiny JSON file that remembers what we've already announced."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, state: dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically so a crash mid-write can't corrupt the file.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
