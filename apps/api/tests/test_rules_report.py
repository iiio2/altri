"""The rules report: every computed value from spec 2.6 on the freshly seeded database."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.report import build_report
from tests.conftest import SEED_NOW

COMMITTED = Path(__file__).resolve().parents[3] / "rules_report.json"


async def test_report_at_seed_now(session: AsyncSession) -> None:
    report = await build_report(session, SEED_NOW)
    lead = report["teams"]["team_lead"]

    assert report["now"] == "2026-11-11T15:00:00Z"
    assert sorted(report["teams"]) == ["team_lead", "team_ops", "team_sales"]
    weeks = list(lead["measurable_status"]["m1"])
    assert (weeks[0], weeks[-1], len(weeks)) == ("2026-08-17", "2026-11-09", 13)
    assert lead["measurable_status"]["m5"]["2026-11-09"] == "on_track"  # current week with a score
    assert lead["measurable_status"]["m5"]["2026-10-19"] == "off_track"  # closed week, no score
    assert lead["measurable_status"]["m1"]["2026-11-09"] == "pending"  # current week, no score
    assert lead["todo_completion"]["2026-11-02"] == {"due": 10, "done": 9, "rate_percent": 90, "meets_target": True}
    assert lead["todo_completion"]["2026-10-26"] == {"due": 3, "done": 2, "rate_percent": 67, "meets_target": False}
    assert lead["todo_completion"]["2026-10-19"] is None
    assert lead["overdue_todos"] == ["t12", "t31"]
    assert lead["rocks"]["r2"] == {"status": "off_track", "progress_percent": 13}
    assert lead["rocks"]["r1"] == {"status": "on_track", "progress_percent": 33}
    assert lead["issue_order"] == ["i2", "i1", "i5", "i3", "i4"]
    assert lead["meetings"]["mt2"] == {
        "scorecard_week": "2026-10-26",
        "measurable_status": {
            "m1": "off_track",
            "m2": "on_track",
            "m3": "on_track",
            "m4": "off_track",
            "m5": "on_track",
        },
        "issues_solved": ["i6"],
        "todos_created": ["t30"],
        "attendee_ids": ["u1", "u2", "u3", "u4", "u5"],
        "rating": 8.3,
    }
    assert json.dumps(lead["meetings"]["mt1"]["rating"]) == "8.0"  # one decimal, even when whole
    assert report["teams"]["team_ops"]["meetings"] == {}


async def test_committed_report_is_current(session: AsyncSession) -> None:
    """rules_report.json at the repo root must match what the code computes for the seed."""
    assert json.loads(COMMITTED.read_text()) == json.loads(json.dumps(await build_report(session, SEED_NOW)))


async def test_report_recomputes_at_another_date(session: AsyncSession) -> None:
    # One second after the week of Nov 9 closes (Monday Nov 16, 00:00:01 Chicago).
    report = await build_report(session, datetime(2026, 11, 16, 6, 0, 1, tzinfo=UTC))
    lead = report["teams"]["team_lead"]

    weeks = list(lead["measurable_status"]["m1"])
    assert (weeks[0], weeks[-1]) == ("2026-08-24", "2026-11-16")
    assert lead["measurable_status"]["m1"]["2026-11-09"] == "off_track"  # now closed with no score
    assert lead["measurable_status"]["m1"]["2026-11-16"] == "pending"
    assert lead["overdue_todos"] == ["t12", "t30", "t31", "t32"]
    assert lead["rocks"]["r1"]["status"] == "off_track"  # ms2 (due Nov 11) is now past due
    assert lead["todo_completion"]["2026-11-09"] == {"due": 3, "done": 0, "rate_percent": 0, "meets_target": False}
