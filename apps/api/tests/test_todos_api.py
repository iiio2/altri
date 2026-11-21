"""To-Dos: overdue flags, last closed week's completion rate, mark done / undo."""

from datetime import UTC, datetime

from httpx import AsyncClient

from tests.conftest import MEMBER, OBSERVER, OPS_MEMBER, login

LEAD = "/api/v1/teams/team_lead"


async def test_list_flags_overdue_and_reports_completion(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    body = (await client.get(f"{LEAD}/todos", headers=headers)).json()

    by_id = {t["id"]: t for t in body["todos"]}
    assert {i for i, t in by_id.items() if t["overdue"]} == {"t12", "t31"}
    assert by_id["t30"]["overdue"] is False  # due today
    assert by_id["t30"]["source_issue"] == {"id": "i6", "title": "Payroll runs, week of Oct 26"}
    assert body["last_closed_week"] == {
        "week_start": "2026-11-02",
        "due": 10,
        "done": 9,  # t29 was done Monday 00:01 Chicago: after its week
        "rate_percent": 90,
        "meets_target": True,
        "target_percent": 90,
    }
    due_dates = [t["due_date"] for t in body["todos"]]
    assert due_dates == sorted(due_dates)


async def test_filters(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)

    open_ = (await client.get(f"{LEAD}/todos", params={"status": "open"}, headers=headers)).json()["todos"]
    in_mt2 = (await client.get(f"{LEAD}/todos", params={"meeting_id": "mt2"}, headers=headers)).json()["todos"]

    assert sorted(t["id"] for t in open_) == ["t12", "t30", "t31", "t32"]
    assert [t["id"] for t in in_mt2] == ["t30"]
    assert (await client.get(f"{LEAD}/todos", params={"status": "nope"}, headers=headers)).status_code == 422


async def test_completion_with_nothing_due_has_no_rate(client: AsyncClient, set_now) -> None:
    set_now(datetime(2026, 9, 2, 15, tzinfo=UTC))  # last closed week Aug 24: nothing due
    headers = await login(client, MEMBER)

    body = (await client.get(f"{LEAD}/todos", headers=headers)).json()

    assert body["last_closed_week"]["due"] == 0
    assert body["last_closed_week"]["rate_percent"] is None
    assert body["last_closed_week"]["meets_target"] is None


async def test_mark_done_and_undo(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    done = await client.patch(f"{LEAD}/todos/t12", json={"done": True}, headers=headers)
    assert (done.json()["done_at"], done.json()["overdue"]) == ("2026-11-11T15:00:00Z", False)

    again = await client.patch(f"{LEAD}/todos/t1", json={"done": True}, headers=headers)
    assert again.json()["done_at"] == "2026-09-14T18:00:00Z"  # already done: keeps the original time

    undone = await client.patch(f"{LEAD}/todos/t12", json={"done": False}, headers=headers)
    assert (undone.json()["done_at"], undone.json()["overdue"]) == (None, True)


async def test_done_flag_must_be_a_boolean(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)
    for body in ({}, {"done": "yes"}, {"done": 1}, {"done": True, "title": "x"}):
        assert (await client.patch(f"{LEAD}/todos/t12", json=body, headers=headers)).status_code == 422, body


async def test_observer_and_outsider_cannot_mark_done(client: AsyncClient) -> None:
    for email in (OBSERVER, OPS_MEMBER):
        headers = await login(client, email)
        assert (await client.patch(f"{LEAD}/todos/t12", json={"done": True}, headers=headers)).status_code == 403


async def test_overdue_todo_can_be_made_an_issue_once(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)

    first = await client.post(f"{LEAD}/todos/t12/issue", headers=headers)
    second = await client.post(f"{LEAD}/todos/t12/issue", headers=headers)
    not_overdue = await client.post(f"{LEAD}/todos/t30/issue", headers=headers)

    assert first.status_code == 201
    assert first.json()["source"] == {"kind": "todo", "todo_id": "t12", "todo_title": "Publish hiring ad"}
    assert (second.status_code, second.json()["id"]) == (200, first.json()["id"])
    assert not_overdue.status_code == 409
