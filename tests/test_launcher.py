"""Единый запуск действительно поднимает API и завершает только свой сервер."""
import socket
from itdesk_core import Api


def test_one_command_launcher(test_mongo, tmp_path, monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = tmp_path / "launcher.ini"
    # Для этого теста новая система, без миграции пользовательской SQLite.
    config.write_text(f"[server]\nport={port}\ndb_path={tmp_path / 'absent.db'}\n"
                      f"[client]\nserver_url=http://127.0.0.1:{port}\n", encoding="utf-8")
    monkeypatch.setenv("ITDESK_CONFIG", str(config))
    import run_app

    def client_session(command):
        api = Api(f"http://127.0.0.1:{port}")
        assert api.health()["storage"] == "MongoDB"
        api.login("tech", "tech123")
        ticket = api.create_ticket(title="Launcher check", description="Real HTTP and MongoDB")
        assert api.document(ticket["id"])["document"]["title"] == "Launcher check"
        return 0

    monkeypatch.setattr(run_app.subprocess, "call", client_session)
    assert run_app.main() == 0
    assert test_mongo.tickets.count_documents({}) == 1
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
