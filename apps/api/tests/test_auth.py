"""Authentication: login, sessions, logout, expiry."""

from datetime import timedelta

from httpx import AsyncClient

from tests.conftest import SEED_NOW, login


async def test_login_sets_httponly_cookie_and_returns_profile(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/login", json={"email": "blake@acme.test"})

    assert res.status_code == 200
    body = res.json()
    assert body["user"] == {"id": "u2", "name": "Blake Brooks", "email": "blake@acme.test", "role": "team_member"}
    assert [t["id"] for t in body["teams"]] == ["team_lead", "team_sales"]
    assert body["can_write"] is True
    assert body["expires_at"] == "2026-11-18T15:00:00Z"  # APP_NOW + 7 days, not the system clock
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("altri_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


async def test_cookie_session_authenticates(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/login", json={"email": "avery@acme.test"})

    res = await client.get("/api/v1/auth/me")

    assert res.status_code == 200
    assert res.json()["user"]["id"] == "u1"


async def test_login_normalizes_email(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/login", json={"email": "  Blake@ACME.Test "})
    assert res.status_code == 200
    assert res.json()["user"]["id"] == "u2"


async def test_login_unknown_email_is_401(client: AsyncClient) -> None:
    res = await client.post("/api/v1/auth/login", json={"email": "nobody@acme.test"})
    assert res.status_code == 401
    assert "set-cookie" not in res.headers


async def test_login_validates_input(client: AsyncClient) -> None:
    for payload in ({}, {"email": "not-an-email"}, {"email": "a b@acme.test"}, {"email": "x" * 300 + "@a.b"}):
        assert (await client.post("/api/v1/auth/login", json=payload)).status_code == 422, payload
    extra = {"email": "blake@acme.test", "role": "admin"}
    assert (await client.post("/api/v1/auth/login", json=extra)).status_code == 422


async def test_me_requires_a_session(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bogus = {"Authorization": "Bearer not-a-real-token"}
    res = await client.get("/api/v1/auth/me", headers=bogus)
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"


async def test_logout_revokes_the_session(client: AsyncClient) -> None:
    headers = await login(client, "blake@acme.test")

    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_relogin_revokes_the_previous_session(client: AsyncClient) -> None:
    first = await login(client, "blake@acme.test")

    res = await client.post("/api/v1/auth/login", json={"email": "casey@acme.test"}, headers=first)

    assert res.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=first)).status_code == 401


async def test_session_expires_exactly_at_expires_at(client: AsyncClient, set_now) -> None:
    headers = await login(client, "blake@acme.test")
    expires_at = SEED_NOW + timedelta(days=7)

    set_now(expires_at - timedelta(seconds=1))
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    set_now(expires_at)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_user_switcher_lists_seeded_users(client: AsyncClient) -> None:
    res = await client.get("/api/v1/auth/users")
    assert res.status_code == 200
    assert [u["id"] for u in res.json()] == [f"u{i}" for i in range(1, 10)]
