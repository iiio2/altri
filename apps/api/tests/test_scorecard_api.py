"""Scorecard: reading, inline edits, Make it an Issue (including concurrent clicks)."""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.models import Issue
from tests.conftest import ADMIN, MEMBER, MEMBER_2, OBSERVER, OPS_MEMBER, login

LEAD = "/api/v1/teams/team_lead"


def cell(scorecard: dict, measurable_id: str, week: str) -> dict:
    row = next(m for m in scorecard["measurables"] if m["id"] == measurable_id)
    return next(c for c in row["cells"] if c["week_start"] == week)


async def test_scorecard_has_13_weeks_ending_with_the_current_one(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    body = (await client.get(f"{LEAD}/scorecard", headers=headers)).json()

    assert body["current_week"] == "2026-11-09"
    assert body["last_closed_week"] == "2026-11-02"
    assert (body["weeks"][0], body["weeks"][-1], len(body["weeks"])) == ("2026-08-17", "2026-11-09", 13)
    assert [m["id"] for m in body["measurables"]] == ["m1", "m2", "m3", "m4", "m5"]
    m3 = body["measurables"][2]
    assert m3["goal"] == {"type": "between", "value": None, "min": 2.0, "max": 4.0}
    assert m3["owner"] == {"id": "u4", "name": "Dana Diaz"}
    assert cell(body, "m1", "2026-11-09")["status"] == "pending"
    assert cell(body, "m5", "2026-10-19") == {
        "measurable_id": "m5",
        "week_start": "2026-10-19",
        "value": None,
        "status": "off_track",  # closed week with no score
        "version": 0,
        "open_issue_id": None,
    }
    assert cell(body, "m1", "2026-11-02")["open_issue_id"] == "i5"


async def test_team_member_cannot_read_another_teams_scorecard(client: AsyncClient) -> None:
    headers = await login(client, OPS_MEMBER)
    assert (await client.get(f"{LEAD}/scorecard", headers=headers)).status_code == 403


async def test_edit_score_updates_status_and_last_save_wins(client: AsyncClient, fresh_data: None) -> None:
    a, b = await login(client, MEMBER), await login(client, MEMBER_2)
    url = f"{LEAD}/measurables/m1/scores/2026-11-09"

    first = await client.put(url, json={"value": 12}, headers=a)
    second = await client.put(url, json={"value": 7.5}, headers=b)

    assert first.json()["status"] == "on_track"
    assert second.status_code == 200
    assert second.json() == {
        "measurable_id": "m1",
        "week_start": "2026-11-09",
        "value": 7.5,
        "status": "off_track",
        "version": 2,
        "open_issue_id": None,
    }
    sc = (await client.get(f"{LEAD}/scorecard", headers=a)).json()
    assert cell(sc, "m1", "2026-11-09")["value"] == 7.5


async def test_clearing_a_score_makes_the_cell_pending_or_off_track(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    res = await client.put(f"{LEAD}/measurables/m5/scores/2026-11-09", json={"value": None}, headers=headers)

    assert res.status_code == 200
    assert (res.json()["value"], res.json()["status"]) == (None, "pending")


async def test_optional_lost_update_protection(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)
    url = f"{LEAD}/measurables/m1/scores/2026-11-02"  # seeded, version 1

    ok = await client.put(url, json={"value": 11, "expected_version": 1}, headers=headers)
    stale = await client.put(url, json={"value": 3, "expected_version": 1}, headers=headers)
    stale_clear = await client.put(url, json={"value": None, "expected_version": 1}, headers=headers)
    new_cell = await client.put(f"{LEAD}/measurables/m1/scores/2026-11-09", json={"value": 3, "expected_version": 0},
                                headers=headers)  # fmt: skip

    assert ok.json()["version"] == 2
    assert stale.status_code == stale_clear.status_code == 409
    assert stale.json()["detail"]["current_version"] == 2
    assert new_cell.status_code == 200


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("m1/scores/2026-11-10", {"value": 1}),  # not a Monday
        ("m1/scores/2026-11-16", {"value": 1}),  # future week
        ("m1/scores/2026-11-09", {"value": "NaN"}),
        ("m1/scores/2026-11-09", {"value": 1e20}),
        ("m1/scores/2026-11-09", {"value": 1.23456}),  # more decimals than stored
        ("m1/scores/2026-11-09", {}),
        ("m1/scores/2026-11-09", {"value": 1, "measurable_id": "m6"}),
        ("m1/scores/not-a-date", {"value": 1}),
    ],
)
async def test_score_input_is_validated(client: AsyncClient, path: str, body: dict) -> None:
    headers = await login(client, MEMBER)
    assert (await client.put(f"{LEAD}/measurables/{path}", json=body, headers=headers)).status_code == 422


async def test_measurable_from_another_team_is_not_found(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)  # member of Sales too, but m6 isn't Leadership's
    res = await client.put(f"{LEAD}/measurables/m6/scores/2026-11-09", json={"value": 1}, headers=headers)
    assert res.status_code == 404


async def test_observer_write_is_refused(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    put = await client.put(f"{LEAD}/measurables/m1/scores/2026-11-09", json={"value": 1}, headers=headers)
    issue = await client.post(f"{LEAD}/measurables/m5/scores/2026-10-19/issue", headers=headers)

    assert put.status_code == issue.status_code == 403


async def test_make_it_an_issue_creates_then_returns_the_existing_one(client: AsyncClient, fresh_data: None) -> None:
    clicker, other = await login(client, MEMBER_2), await login(client, MEMBER)
    url = f"{LEAD}/measurables/m5/scores/2026-10-19/issue"  # off track: no score in a closed week

    created = await client.post(url, headers=clicker)
    again = await client.post(url, headers=other)

    assert created.status_code == 201
    issue = created.json()
    assert issue["title"] == "Cash on hand, week of Oct 19"
    assert issue["owner"]["id"] == "u3"  # the user who clicked
    assert issue["source"] == {
        "kind": "score",
        "measurable_id": "m5",
        "measurable_name": "Cash on hand",
        "week_start": "2026-10-19",
    }
    assert (again.status_code, again.json()["id"]) == (200, issue["id"])
    sc = (await client.get(f"{LEAD}/scorecard", headers=other)).json()
    assert cell(sc, "m5", "2026-10-19")["open_issue_id"] == issue["id"]


async def test_make_it_an_issue_returns_the_seeded_unsolved_issue(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)
    res = await client.post(f"{LEAD}/measurables/m1/scores/2026-11-02/issue", headers=headers)
    assert (res.status_code, res.json()["id"]) == (200, "i5")
    edit = await client.put(f"{LEAD}/measurables/m1/scores/2026-11-02", json={"value": 9}, headers=headers)
    assert edit.json()["open_issue_id"] == "i5"


async def test_make_it_an_issue_after_solving_creates_a_new_one(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)
    url = f"{LEAD}/measurables/m4/scores/2026-10-26/issue"  # i6 was raised for this cell and is solved

    res = await client.post(url, headers=headers)

    assert res.status_code == 201
    assert res.json()["id"] != "i6"


@pytest.mark.parametrize(
    ("cell_path", "reason"),
    [("m1/scores/2026-10-19", "on_track"), ("m1/scores/2026-11-09", "pending")],
)
async def test_only_off_track_cells_can_be_made_an_issue(client: AsyncClient, cell_path: str, reason: str) -> None:
    headers = await login(client, MEMBER)
    res = await client.post(f"{LEAD}/measurables/{cell_path}/issue", headers=headers)
    assert res.status_code == 409
    assert reason in res.json()["detail"]


async def test_concurrent_make_it_an_issue_returns_one_issue(
    fresh_data: None, client: AsyncClient, session: AsyncSession
) -> None:
    """Many users click at the same moment: each request runs on its own DB connection, truly in parallel."""
    users = [await login(client, e) for e in (ADMIN, MEMBER, MEMBER_2, "dana@acme.test")] * 3
    url = f"{LEAD}/measurables/m5/scores/2026-11-02/issue"

    responses = await asyncio.gather(*(client.post(url, headers=h) for h in users))

    assert all(r.status_code in (200, 201) for r in responses), [r.text for r in responses]
    assert sorted(r.status_code for r in responses).count(201) == 1
    assert len({r.json()["id"] for r in responses}) == 1
    count = await session.scalar(
        select(func.count()).select_from(Issue).where(Issue.source_measurable_id == "m5", Issue.solved_at.is_(None))
    )
    assert count == 1
