"""Rocks: read-only, current quarter, computed status and progress."""

from datetime import UTC, datetime

from httpx import AsyncClient

from tests.conftest import MEMBER, OBSERVER, login

LEAD = "/api/v1/teams/team_lead"


async def test_rocks_show_computed_status_progress_and_milestones(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    body = (await client.get(f"{LEAD}/rocks", headers=headers)).json()

    assert body["quarter"] == "2026-Q4"
    rocks = {r["id"]: r for r in body["rocks"]}
    assert {i: (r["status"], r["progress_percent"]) for i, r in rocks.items()} == {
        "r1": ("on_track", 33),  # ms2 due today: not past due
        "r2": ("off_track", 13),  # ms5 due yesterday, not done; 1/8 = 12.5% -> 13%
        "r3": ("complete", 100),
        "r4": ("off_track", 0),
        "r5": ("on_track", 0),
    }
    assert rocks["r2"]["seeded_status"] == "on_track"
    ms5 = next(m for m in rocks["r2"]["milestones"] if m["id"] == "ms5")
    assert ms5 == {"id": "ms5", "title": "Shortlist of 5", "due_date": "2026-11-10", "done": False, "past_due": True}


async def test_other_quarters_are_filtered(client: AsyncClient, set_now) -> None:
    set_now(datetime(2027, 1, 5, 15, tzinfo=UTC))  # before signing in: sessions expire after 7 days
    headers = await login(client, MEMBER)

    assert (await client.get(f"{LEAD}/rocks", headers=headers)).json() == {"quarter": "2027-Q1", "rocks": []}
    q4 = (await client.get(f"{LEAD}/rocks", params={"quarter": "2026-Q4"}, headers=headers)).json()
    assert len(q4["rocks"]) == 5
    assert (await client.get(f"{LEAD}/rocks", params={"quarter": "Q4"}, headers=headers)).status_code == 422


async def test_rocks_are_read_only(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await client.request(method, f"{LEAD}/rocks", headers=headers)).status_code == 405


async def test_off_track_rock_can_be_made_an_issue_once(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    first = await client.post(f"{LEAD}/rocks/r2/issue", headers=headers)
    second = await client.post(f"{LEAD}/rocks/r2/issue", headers=headers)
    on_track = await client.post(f"{LEAD}/rocks/r1/issue", headers=headers)
    observer = await client.post(f"{LEAD}/rocks/r4/issue", headers=await login(client, OBSERVER))

    assert (first.status_code, first.json()["title"]) == (201, "Off-track Rock: Hire VP of Sales")
    assert (second.status_code, second.json()["id"]) == (200, first.json()["id"])
    assert on_track.status_code == 409
    assert observer.status_code == 403
