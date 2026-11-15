"""Тесты конфигурации, health-check и администрирования (п.13, п.16)."""
import pytest
from fastapi.testclient import TestClient

import manage
from itdesk_core import base_dir, db_path, load_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ITDESK_DB", str(tmp_path / "test.db"))
    from server.main import app
    with TestClient(app) as c:
        yield c


def login(client, name, pw):
    return client.post("/auth/login", json={"username": name, "password": pw})


def test_config_defaults_and_override(tmp_path):
    assert load_config(tmp_path / "none.ini")["server"]["port"] == "8000"
    f = tmp_path / "c.ini"
    f.write_text("[server]\nport = 9999\n", encoding="utf-8")
    cfg = load_config(f)
    assert cfg["server"]["port"] == "9999" and cfg["server"]["host"] == "127.0.0.1"


def test_db_path_env_override_and_default(monkeypatch):
    monkeypatch.setenv("ITDESK_DB", "/tmp/x.db")
    assert db_path() == "/tmp/x.db"
    monkeypatch.delenv("ITDESK_DB")
    assert db_path() == str(base_dir() / "itdesk.db")


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_set_password_invalidates_sessions(client):
    token = login(client, "tech", "tech123").json()["token"]
    manage.set_password("tech", "newpass1")
    assert client.get("/tickets", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert login(client, "tech", "tech123").status_code == 401
    assert login(client, "tech", "newpass1").status_code == 200


def test_set_role_gives_staff_access(client):
    client.post("/auth/register", json={"username": "newstaff", "password": "secret1"})
    h = {"Authorization": f"Bearer {login(client, 'newstaff', 'secret1').json()['token']}"}
    assert client.get("/stats", headers=h).status_code == 403
    manage.set_role("newstaff", "tech")
    h = {"Authorization": f"Bearer {login(client, 'newstaff', 'secret1').json()['token']}"}
    assert client.get("/stats", headers=h).status_code == 200


def test_manage_validation(client):
    with pytest.raises(ValueError):
        manage.set_password("tech", "123")
    with pytest.raises(ValueError):
        manage.set_role("tech", "boss")
    with pytest.raises(ValueError):
        manage.set_role("ghost", "tech")
