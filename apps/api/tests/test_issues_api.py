"""Issues: listing in Issue order, create, priority, solve, follow-up To-Dos."""

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, MEMBER, MEMBER_2, OBSERVER, OPS_MEMBER, login

LEAD = "/api/v1/teams/team_lead"


async def test_open_issues_are_in_issue_order(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    issues = (await client.get(f"{LEAD}/issues", headers=headers)).json()

    # p5 oldest first (i2 Oct 14, i1 Oct 20), then p4, p3, and no priority last.
    assert [i["id"] for i in issues] == ["i2", "i1", "i5", "i3", "i4"]
    i5 = issues[2]
    assert i5["source"] == {
        "kind": "score",
        "measurable_id": "m1",
        "measurable_name": "New deals closed",
        "week_start": "2026-11-02",
    }
    assert i5["created_at"] == "2026-11-09T16:00:00Z"
    assert issues[0]["source"] is None


async def test_solved_issues_are_listed_separately_with_note(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)

    solved = (await client.get(f"{LEAD}/issues", params={"status": "solved"}, headers=headers)).json()

    assert [i["id"] for i in solved] == ["i6", "i7"]  # most recently solved first
    assert solved[0]["resolution_note"] == "Bank holiday moved the run; added a reminder."
    assert solved[0]["solved_at"] == "2026-11-04T15:40:00Z"
    assert solved[0]["solved_in_meeting_id"] == "mt2"


async def test_create_issue_owner_is_the_creator(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER_2)

    res = await client.post(f"{LEAD}/issues", json={"title": "  Vendor invoices late  "}, headers=headers)

    assert res.status_code == 201
    body = res.json()
    assert (body["title"], body["owner"]["id"], body["priority"], body["source"]) == (
        "Vendor invoices late",
        "u3",
        None,
        None,
    )
    assert body["created_at"] == "2026-11-11T15:00:00Z"
    ids = [i["id"] for i in (await client.get(f"{LEAD}/issues", headers=headers)).json()]
    assert ids[-1] == body["id"]  # no priority, newest: last


async def test_admin_can_create_in_a_team_they_are_not_in(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, ADMIN)
    res = await client.post("/api/v1/teams/team_ops/issues", json={"title": "Dock scheduling"}, headers=headers)
    assert (res.status_code, res.json()["owner"]["id"]) == (201, "u1")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"title": "ok", "priority": 0},
        {"title": "ok", "priority": 6},
        {"title": "ok", "priority": "5"},
        {"title": "ok", "priority": 2.5},
        {"title": "ok", "owner_id": "u1"},  # owner is always the creator
    ],
)
async def test_create_issue_validates_input(client: AsyncClient, body: dict) -> None:
    headers = await login(client, MEMBER)
    assert (await client.post(f"{LEAD}/issues", json=body, headers=headers)).status_code == 422


async def test_set_priority_reorders(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    res = await client.patch(f"{LEAD}/issues/i4", json={"priority": 5}, headers=headers)

    assert (res.status_code, res.json()["priority"], res.json()["version"]) == (200, 5, 2)
    ids = [i["id"] for i in (await client.get(f"{LEAD}/issues", headers=headers)).json()]
    assert ids == ["i4", "i2", "i1", "i5", "i3"]  # Sep 1: now the oldest priority 5


async def test_priority_lost_update_protection(client: AsyncClient, fresh_data: None) -> None:
    a, b = await login(client, MEMBER), await login(client, MEMBER_2)

    first = await client.patch(f"{LEAD}/issues/i3", json={"priority": 4, "expected_version": 1}, headers=a)
    stale = await client.patch(f"{LEAD}/issues/i3", json={"priority": 1, "expected_version": 1}, headers=b)
    last_wins = await client.patch(f"{LEAD}/issues/i3", json={"priority": 1}, headers=b)

    assert first.status_code == 200
    assert (stale.status_code, stale.json()["detail"]["current_version"]) == (409, 2)
    assert last_wins.json()["priority"] == 1


async def test_solve_requires_a_note_and_happens_once(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    assert (await client.post(f"{LEAD}/issues/i3/solve", json={}, headers=headers)).status_code == 422
    blank = await client.post(f"{LEAD}/issues/i3/solve", json={"resolution_note": "  "}, headers=headers)
    assert blank.status_code == 422
    res = await client.post(f"{LEAD}/issues/i3/solve", json={"resolution_note": "Hired a contractor"}, headers=headers)
    again = await client.post(f"{LEAD}/issues/i3/solve", json={"resolution_note": "x"}, headers=headers)
    priority = await client.patch(f"{LEAD}/issues/i3", json={"priority": 1}, headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert (body["solved_at"], body["resolution_note"], body["solved_in_meeting_id"]) == (
        "2026-11-11T15:00:00Z",
        "Hired a contractor",
        None,  # no meeting running
    )
    assert again.status_code == priority.status_code == 409
    assert "i3" not in [i["id"] for i in (await client.get(f"{LEAD}/issues", headers=headers)).json()]


async def test_add_todo_to_issue_due_in_seven_days(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    res = await client.post(
        f"{LEAD}/issues/i1/todos", json={"title": "Post the job", "owner_id": "u3"}, headers=headers
    )

    assert res.status_code == 201
    todo = res.json()
    assert (todo["due_date"], todo["owner"]["id"], todo["source_issue"], todo["overdue"]) == (
        "2026-11-18",  # today (Nov 11, company time) + 7
        "u3",
        {"id": "i1", "title": "Hiring pipeline is slow"},
        False,
    )


@pytest.mark.parametrize(
    ("owner_id", "why"),
    [("u5", "observer"), ("u8", "not in the team"), ("u404", "unknown")],
)
async def test_todo_owner_must_be_a_team_admin_or_member(client: AsyncClient, owner_id: str, why: str) -> None:
    headers = await login(client, MEMBER)
    res = await client.post(f"{LEAD}/issues/i1/todos", json={"title": "x", "owner_id": owner_id}, headers=headers)
    assert res.status_code == 422, why


async def test_admin_outside_the_team_can_own_todos(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, OPS_MEMBER)
    team = (await client.get("/api/v1/teams/team_ops", headers=headers)).json()
    assert [u["id"] for u in team["owner_candidates"]] == ["u1", "u4", "u8", "u9"]  # Admin u1 is not a member

    res = await client.post("/api/v1/teams/team_ops/issues/i9/todos", json={"title": "x", "owner_id": "u1"},
                            headers=headers)  # fmt: skip
    assert res.status_code == 201


async def test_issue_in_another_team_is_not_found(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)  # member of Leadership and Sales
    assert (
        await client.post(f"{LEAD}/issues/i8/solve", json={"resolution_note": "x"}, headers=headers)
    ).status_code == 404
    assert (await client.get(f"{LEAD}/issues/i8", headers=headers)).status_code == 404


async def test_observer_and_outsider_writes_are_refused(client: AsyncClient) -> None:
    observer, outsider = await login(client, OBSERVER), await login(client, OPS_MEMBER)
    for headers in (observer, outsider):
        assert (await client.post(f"{LEAD}/issues", json={"title": "x"}, headers=headers)).status_code == 403
        assert (await client.patch(f"{LEAD}/issues/i1", json={"priority": 1}, headers=headers)).status_code == 403
        solve = await client.post(f"{LEAD}/issues/i1/solve", json={"resolution_note": "x"}, headers=headers)
        assert solve.status_code == 403
        todo = await client.post(f"{LEAD}/issues/i1/todos", json={"title": "x", "owner_id": "u2"}, headers=headers)
        assert todo.status_code == 403
