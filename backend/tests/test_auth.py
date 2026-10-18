import re

from app.emailer import OUTBOX


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_signup_login_me(client):
    r = client.post("/api/auth/signup", json={"email": "Alice@Example.com", "password": "password123", "name": "Alice"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["email"] == "alice@example.com"

    assert client.post("/api/auth/signup", json={"email": "alice@example.com", "password": "password123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "ALICE@example.com", "password": "password123"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Alice"


def test_signup_validation(client):
    assert client.post("/api/auth/signup", json={"email": "not-an-email", "password": "password123"}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_password_reset_flow(client, user):
    OUTBOX.clear()
    r = client.post("/api/auth/forgot-password", json={"email": user["email"]})
    assert r.status_code == 200
    # Unknown emails get the same answer and no mail.
    assert client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 200
    assert len(OUTBOX) == 1
    token = re.search(r"token=([\w-]+)", OUTBOX[0].get_content()).group(1)

    assert client.post("/api/auth/reset-password", json={"token": "x" * 20, "password": "newpassword1"}).status_code == 400
    r = client.post("/api/auth/reset-password", json={"token": token, "password": "newpassword1"})
    assert r.status_code == 200
    # Token cannot be reused, and the new password works.
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "another-pass"}).status_code == 400
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "newpassword1"}).status_code == 200


def test_rate_limit(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 2)
    codes = [
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever1"}, headers={"X-Real-IP": "10.9.9.9"}).status_code
        for _ in range(4)
    ]
    assert 429 in codes
