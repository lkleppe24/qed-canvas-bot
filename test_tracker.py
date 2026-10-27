from datetime import datetime, timedelta, timezone

from tracker import StateStore, find_new_submissions, pending_group_assignments

COURSE = {"id": 101, "name": "CS 161"}


def assignment(aid, group=True, state="unsubmitted", submitted_at=None, attempt=None, due=None, late=False):
    return {
        "id": aid,
        "name": f"Project {aid}",
        "html_url": f"https://canvas.example.edu/courses/101/assignments/{aid}",
        "group_category_id": 7 if group else None,
        "due_at": due,
        "submission": {"workflow_state": state, "submitted_at": submitted_at,
                       "attempt": attempt, "late": late},
    }


def test_new_group_submission_detected_once():
    state = {}
    a = [assignment(1, state="submitted", submitted_at="2026-10-26T20:00:00Z", attempt=1)]
    first = find_new_submissions(COURSE, a, state)
    assert len(first) == 1 and first[0].assignment_name == "Project 1"
    assert find_new_submissions(COURSE, a, state) == []  # not announced twice


def test_unsubmitted_and_individual_ignored():
    state = {}
    a = [assignment(1), assignment(2, group=False, state="submitted",
                                   submitted_at="2026-10-26T20:00:00Z", attempt=1)]
    assert find_new_submissions(COURSE, a, state) == []
    assert len(find_new_submissions(COURSE, a, state, group_only=False)) == 1


def test_resubmission_and_graded():
    state = {"101:1": 1}
    a = [assignment(1, state="graded", submitted_at="2026-10-26T21:00:00Z", attempt=2, late=True)]
    subs = find_new_submissions(COURSE, a, state)
    assert len(subs) == 1 and subs[0].is_resubmission and subs[0].late
    assert state["101:1"] == 2


def test_pending_lists_only_future_unsubmitted_group_work():
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    a = [assignment(1, due=future), assignment(2, due=past),
         assignment(3, due=future, state="submitted", submitted_at=past, attempt=1),
         assignment(4, group=False, due=future)]
    assert [p["name"] for p in pending_group_assignments(COURSE, a)] == ["Project 1"]


def test_state_store_roundtrip(tmp_path):
    store = StateStore(tmp_path / "data" / "state.json")
    assert not store.exists() and store.load() == {}
    store.save({"101:1": 1})
    assert store.exists() and store.load() == {"101:1": 1}
