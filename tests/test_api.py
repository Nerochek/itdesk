"""Модульные тесты API (п.13). Запуск: pytest"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ITDESK_DB", str(tmp_path / "test.db"))
    from server.main import app
    with TestClient(app) as c:
        yield c


def auth(client, name, pw, register=False):
    if register:
        assert client.post("/auth/register", json={"username": name, "password": pw}).status_code == 201
    r = client.post("/auth/login", json={"username": name, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


TICKET = {"title": "Не работает проектор", "description": "Нет изображения", "category": "projector"}


def test_requires_auth(client):
    assert client.get("/tickets").status_code == 401


def test_register_duplicate_and_wrong_password(client):
    auth(client, "student1", "secret1", register=True)
    assert client.post("/auth/register", json={"username": "student1", "password": "secret1"}).status_code == 409
    assert client.post("/auth/login", json={"username": "student1", "password": "bad_pw"}).status_code == 401


def test_validation(client):
    h = auth(client, "student1", "secret1", register=True)
    assert client.post("/tickets", json={**TICKET, "priority": "urgent"}, headers=h).status_code == 422


def test_user_sees_only_own_tickets(client):
    a = auth(client, "alice", "secret1", register=True)
    b = auth(client, "bob", "secret1", register=True)
    tid = client.post("/tickets", json=TICKET, headers=a).json()["id"]
    assert len(client.get("/tickets", headers=a).json()) == 1
    assert client.get("/tickets", headers=b).json() == []
    assert client.get(f"/tickets/{tid}", headers=b).status_code == 404


def test_user_cannot_change_status_or_see_stats(client):
    a = auth(client, "alice", "secret1", register=True)
    tid = client.post("/tickets", json=TICKET, headers=a).json()["id"]
    assert client.patch(f"/tickets/{tid}", json={"status": "closed"}, headers=a).status_code == 403
    assert client.get("/stats", headers=a).status_code == 403


def test_staff_workflow(client):
    a = auth(client, "alice", "secret1", register=True)
    t = auth(client, "tech", "tech123")
    tid = client.post("/tickets", json=TICKET, headers=a).json()["id"]
    assert client.patch(f"/tickets/{tid}", json={"status": "in_progress"}, headers=t).status_code == 200
    client.post(f"/tickets/{tid}/comments", json={"text": "Выезжаю"}, headers=t)
    d = client.get(f"/tickets/{tid}", headers=a).json()
    assert d["status"] == "in_progress" and len(d["comments"]) == 1 and len(d["history"]) == 2
    assert client.get("/stats", headers=t).json()["by_status"] == {"in_progress": 1}
    assert "Не работает проектор" in client.get("/export.csv", headers=t).text


def test_assignee_must_be_staff(client):
    a = auth(client, "alice", "secret1", register=True)
    t = auth(client, "tech", "tech123")
    tid = client.post("/tickets", json=TICKET, headers=a).json()["id"]
    assert client.patch(f"/tickets/{tid}", json={"assignee_id": 999}, headers=t).status_code == 400
