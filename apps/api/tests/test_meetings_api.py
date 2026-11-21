"""Level 10 Meeting: control, server-owned timer, rating, summary."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, MEMBER, MEMBER_2, OBSERVER, OPS_MEMBER, SEED_NOW, login

LEAD = "/api/v1/teams/team_lead"
MEETINGS = f"{LEAD}/meetings"


async def start(client: AsyncClient, headers: dict[str, str], team_url: str = LEAD) -> dict:
    res = await client.post(f"{team_url}/meetings", headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def test_start_makes_the_caller_facilitator(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER_2)

    m = await start(client, headers)

    assert (m["status"], m["facilitator"]["id"], m["section"]) == ("active", "u3", "scorecard")
    assert m["scorecard_week"] == "2026-11-02"  # the last closed week
    assert [a["id"] for a in m["attendees"]] == ["u3"]
    assert [(a["section"], a["duration_seconds"]) for a in m["agenda"]] == [
        ("scorecard", 300),
        ("ids", 3600),
        ("conclude", 600),
    ]
    assert (m["section_elapsed_seconds"], m["over_time"], m["server_now"]) == (0, False, "2026-11-11T15:00:00Z")
    active = (await client.get(f"{MEETINGS}/active", headers=headers)).json()
    assert active["id"] == m["id"]


async def test_no_active_meeting_is_null(client: AsyncClient) -> None:
    headers = await login(client, MEMBER)
    res = await client.get(f"{MEETINGS}/active", headers=headers)
    assert (res.status_code, res.json()) == (200, None)


async def test_one_active_meeting_per_team(client: AsyncClient, fresh_data: None) -> None:
    a, b = await login(client, MEMBER), await login(client, MEMBER_2)
    first = await start(client, a)

    second = await client.post(MEETINGS, headers=b)

    assert second.status_code == 409
    assert second.json()["detail"]["meeting_id"] == first["id"]
    assert (await start(client, await login(client, OPS_MEMBER), "/api/v1/teams/team_ops"))["status"] == "active"


@pytest.mark.parametrize(("email", "status"), [(OBSERVER, 403), (OPS_MEMBER, 403)])
async def test_observers_and_outsiders_cannot_start(client: AsyncClient, email: str, status: int) -> None:
    assert (await client.post(MEETINGS, headers=await login(client, email))).status_code == status


async def test_admin_can_run_a_meeting_in_any_team(client: AsyncClient, fresh_data: None) -> None:
    m = await start(client, await login(client, ADMIN), "/api/v1/teams/team_sales")
    assert m["facilitator"]["id"] == "u1"


async def test_anyone_who_can_read_the_team_can_join(client: AsyncClient, fresh_data: None) -> None:
    m = await start(client, await login(client, MEMBER))
    observer = await login(client, OBSERVER)

    joined = await client.post(f"{MEETINGS}/{m['id']}/join", headers=observer)
    twice = await client.post(f"{MEETINGS}/{m['id']}/join", headers=observer)
    outsider = await client.post(f"{MEETINGS}/{m['id']}/join", headers=await login(client, OPS_MEMBER))

    assert joined.status_code == twice.status_code == 200
    assert [(a["id"], a["role"]) for a in twice.json()["attendees"]] == [("u2", "team_member"), ("u5", "observer")]
    assert outsider.status_code == 403


async def test_only_the_facilitator_moves_sections_and_ends(client: AsyncClient, fresh_data: None) -> None:
    facilitator = await login(client, MEMBER)
    m = await start(client, facilitator)
    url = f"{MEETINGS}/{m['id']}"

    for email in (MEMBER_2, ADMIN, OBSERVER):
        other = await login(client, email)
        assert (await client.put(f"{url}/section", json={"section": "ids"}, headers=other)).status_code == 403
        assert (await client.post(f"{url}/end", headers=other)).status_code == 403

    res = await client.put(f"{url}/section", json={"section": "ids"}, headers=facilitator)
    assert (res.status_code, res.json()["section"]) == (200, "ids")


async def test_server_owned_timer_shows_over_time_and_never_advances(
    client: AsyncClient, fresh_data: None, set_now
) -> None:
    headers = await login(client, MEMBER)
    m = await start(client, headers)
    url = f"{MEETINGS}/{m['id']}"

    set_now(SEED_NOW + timedelta(minutes=5))
    at_limit = (await client.get(url, headers=headers)).json()
    set_now(SEED_NOW + timedelta(minutes=7, seconds=30))
    overrun = (await client.get(url, headers=headers)).json()

    assert (at_limit["section_elapsed_seconds"], at_limit["over_time"]) == (300, False)
    assert (overrun["section"], overrun["section_elapsed_seconds"], overrun["over_time"]) == ("scorecard", 450, True)

    moved = (await client.put(f"{url}/section", json={"section": "ids"}, headers=headers)).json()
    assert (moved["section_started_at"], moved["section_elapsed_seconds"], moved["over_time"]) == (
        "2026-11-11T15:07:30Z",
        0,
        False,
    )
    set_now(SEED_NOW + timedelta(minutes=9))
    repeat = (await client.put(f"{url}/section", json={"section": "ids"}, headers=headers)).json()
    assert repeat["section_started_at"] == "2026-11-11T15:07:30Z"  # a repeated click doesn't reset the timer


async def test_rating_rules(client: AsyncClient, fresh_data: None) -> None:
    facilitator, member, observer = (
        await login(client, MEMBER),
        await login(client, MEMBER_2),
        await login(client, OBSERVER),
    )
    m = await start(client, facilitator)
    url = f"{MEETINGS}/{m['id']}"
    await client.post(f"{url}/join", headers=observer)

    too_early = await client.put(f"{url}/rating", json={"rating": 8}, headers=facilitator)
    await client.put(f"{url}/section", json={"section": "conclude"}, headers=facilitator)
    not_joined = await client.put(f"{url}/rating", json={"rating": 8}, headers=member)
    by_observer = await client.put(f"{url}/rating", json={"rating": 8}, headers=observer)
    await client.post(f"{url}/join", headers=member)
    for bad in (0, 11, 7.5, "8"):
        assert (await client.put(f"{url}/rating", json={"rating": bad}, headers=member)).status_code == 422
    await client.put(f"{url}/rating", json={"rating": 7}, headers=member)
    await client.put(f"{url}/rating", json={"rating": 9}, headers=facilitator)
    changed = await client.put(f"{url}/rating", json={"rating": 10}, headers=member)

    assert too_early.status_code == 409
    assert not_joined.status_code == 409
    assert by_observer.status_code == 403
    assert changed.json()["ratings"] == [{"user_id": "u2", "rating": 9}, {"user_id": "u3", "rating": 10}]
    assert changed.json()["average_rating"] == 9.5


async def test_end_returns_the_summary_and_freezes_the_meeting(client: AsyncClient, fresh_data: None, set_now) -> None:
    facilitator, member, observer = (
        await login(client, MEMBER),
        await login(client, MEMBER_2),
        await login(client, OBSERVER),
    )
    # A To-Do created before the meeting must not show up in its summary.
    await client.post(f"{LEAD}/issues/i1/todos", json={"title": "before", "owner_id": "u2"}, headers=facilitator)
    set_now(SEED_NOW + timedelta(minutes=1))
    m = await start(client, facilitator)
    url = f"{MEETINGS}/{m['id']}"
    await client.post(f"{url}/join", headers=member)
    await client.post(f"{url}/join", headers=observer)

    await client.put(f"{url}/section", json={"section": "ids"}, headers=facilitator)
    solved = await client.post(f"{LEAD}/issues/i2/solve", json={"resolution_note": "Exec sponsor"}, headers=member)
    todo = await client.post(f"{LEAD}/issues/i2/todos", json={"title": "Call A", "owner_id": "u3"}, headers=member)
    await client.put(f"{url}/section", json={"section": "conclude"}, headers=facilitator)
    await client.put(f"{url}/rating", json={"rating": 8}, headers=facilitator)
    await client.put(f"{url}/rating", json={"rating": 9}, headers=member)
    set_now(SEED_NOW + timedelta(minutes=70))
    ended = await client.post(f"{url}/end", headers=facilitator)

    assert solved.json()["solved_in_meeting_id"] == m["id"]
    assert todo.json()["created_in_meeting_id"] == m["id"]
    assert ended.status_code == 200
    summary = ended.json()
    assert summary["scorecard_week"] == "2026-11-02"
    assert {x["id"]: x["status"] for x in summary["measurables"]} == {
        "m1": "off_track",
        "m2": "on_track",
        "m3": "off_track",
        "m4": "on_track",
        "m5": "off_track",
    }
    assert [i["id"] for i in summary["issues_solved"]] == ["i2"]
    assert [t["id"] for t in summary["todos_created"]] == [todo.json()["id"]]
    assert [a["id"] for a in summary["attendees"]] == ["u2", "u3", "u5"]
    assert (summary["average_rating"], summary["ended_at"]) == (8.5, "2026-11-11T16:10:00Z")
    assert (await client.get(f"{url}/summary", headers=observer)).json() == summary

    for res in (
        await client.put(f"{url}/rating", json={"rating": 3}, headers=member),
        await client.post(f"{url}/join", headers=member),
        await client.put(f"{url}/section", json={"section": "ids"}, headers=facilitator),
        await client.post(f"{url}/end", headers=facilitator),
    ):
        assert res.status_code == 409
    assert (await client.get(f"{MEETINGS}/active", headers=member)).json() is None
    assert (await client.post(MEETINGS, headers=member)).status_code == 201  # next week's meeting can start


async def test_summary_of_a_running_meeting_is_a_conflict(client: AsyncClient, fresh_data: None) -> None:
    headers = await login(client, MEMBER)
    m = await start(client, headers)
    assert (await client.get(f"{MEETINGS}/{m['id']}/summary", headers=headers)).status_code == 409


async def test_seeded_meeting_summaries(client: AsyncClient) -> None:
    headers = await login(client, OBSERVER)

    mt1 = (await client.get(f"{MEETINGS}/mt1/summary", headers=headers)).json()
    mt2 = (await client.get(f"{MEETINGS}/mt2/summary", headers=headers)).json()
    listed = (await client.get(MEETINGS, headers=headers)).json()

    assert (mt1["scorecard_week"], mt1["average_rating"]) == ("2026-10-19", 8.0)
    assert ([i["id"] for i in mt1["issues_solved"]], [t["id"] for t in mt1["todos_created"]]) == (["i7"], ["t20"])
    assert (mt2["scorecard_week"], mt2["average_rating"]) == ("2026-10-26", 8.3)
    assert ([i["id"] for i in mt2["issues_solved"]], [t["id"] for t in mt2["todos_created"]]) == (["i6"], ["t30"])
    assert [a["id"] for a in mt2["attendees"]] == ["u1", "u2", "u3", "u4", "u5"]
    assert [(m["id"], m["status"]) for m in listed] == [("mt2", "ended"), ("mt1", "ended")]


async def test_meetings_of_another_team_are_refused(client: AsyncClient) -> None:
    headers = await login(client, OPS_MEMBER)
    assert (await client.get(f"{MEETINGS}/mt1/summary", headers=headers)).status_code == 403
    assert (await client.get(f"{MEETINGS}/mt1", headers=headers)).status_code == 403
    own_team = await client.get("/api/v1/teams/team_ops/meetings/mt1/summary", headers=headers)
    assert own_team.status_code == 404  # mt1 is Leadership's
