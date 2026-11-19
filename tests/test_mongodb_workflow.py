"""Проверка документов MongoDB и полного сценария кнопок приложения."""
import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server import db
from server.main import app
from server.processing import RUNS


@pytest.fixture
def client(test_mongo):
    with TestClient(app) as client:
        yield client


def auth(client, name="tech", password="tech123"):
    response = client.post("/auth/login", json={"username": name, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def job(client, headers, action):
    response = client.post("/processing/jobs", headers=headers, json={"action": action})
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = client.get(f"/processing/jobs/{identifier}", headers=headers).json()
        if state["status"] != "running":
            assert state["status"] == "done", state
            return identifier, state
        time.sleep(0.1)
    pytest.fail("Обработка не завершилась за 180 секунд")


def test_document_crud_and_permissions(client, test_mongo):
    tech = auth(client)
    client.post("/auth/register", json={"username": "student", "password": "secret1"})
    student = auth(client, "student", "secret1")
    ticket = {"title": "Проектор 205", "description": "Не работает", "category": "projector"}
    tid = client.post("/tickets", headers=student, json=ticket).json()["id"]
    assert test_mongo.tickets.find_one({"id": tid})["title"] == ticket["title"]
    assert client.get(f"/tickets/{tid}/document", headers=student).status_code == 403
    assert client.delete(f"/tickets/{tid}", headers=student).status_code == 403
    assert client.get("/processing/jobs/" + "a" * 32, headers=student).status_code == 403
    # Неверный исполнитель не должен частично менять документ.
    response = client.patch(f"/tickets/{tid}", headers=tech, json={"status": "closed", "assignee_id": 99999})
    assert response.status_code == 400
    assert test_mongo.tickets.find_one({"id": tid})["status"] == "new"
    client.patch(f"/tickets/{tid}", headers=tech, json={"status": "in_progress"})
    document = client.get(f"/tickets/{tid}/document", headers=tech).json()
    assert document["collection"] == "tickets"
    assert document["document"]["status"] == "in_progress"
    assert "password_hash" not in json.dumps(document)
    assert len(client.get("/tickets", headers=tech, params={"q": "205"}).json()) == 1
    assert client.delete(f"/tickets/{tid}", headers=tech).status_code == 200
    assert test_mongo.tickets.find_one({"id": tid}) is None


def test_processing_buttons_end_to_end(client, test_mongo):
    headers = auth(client)
    identifier, state = job(client, headers, "seed")
    assert test_mongo.tickets.count_documents({"source": "demo"}) == 1000
    job(client, headers, "seed")
    assert test_mongo.tickets.count_documents({}) == 1000
    job(client, headers, "import")
    assert test_mongo.external_raw.count_documents({}) == 200
    assert test_mongo.tickets.count_documents({"source": "jsonplaceholder"}) == 200
    identifier, state = job(client, headers, "all")
    assert len(state["result"]["messages"]) == 5
    files = state["result"]["files"]
    for name in ("dashboard.png", "spark_sql.json", "hadoop_result.json", "mongo_explain.json"):
        assert name in files
        assert client.get(f"/processing/jobs/{identifier}/files/{name}", headers=headers).status_code == 200
    hadoop = client.get(f"/processing/jobs/{identifier}/files/hadoop_result.json", headers=headers).json()
    assert hadoop["equal"] is True and hadoop["engine"] == "Apache Hadoop Streaming"
    assert (RUNS / identifier / "hadoop-output/_SUCCESS").is_file()
    assert client.get(f"/processing/jobs/{identifier}/files/source.jsonl", headers=headers).status_code == 404


def test_import_preserves_edited_documents(client, test_mongo, monkeypatch):
    from analytics.application import add_document
    assert add_document(test_mongo, "jsonplaceholder", 1, "Imported", "new")
    test_mongo.tickets.update_one({"source_id": 1}, {"$set": {"status": "closed"}})
    assert not add_document(test_mongo, "jsonplaceholder", 1, "Reset", "new")
    assert test_mongo.tickets.find_one({"source_id": 1})["status"] == "closed"


def test_gui_displays_mongo_tickets_and_processing_results(client, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from itdesk_core.client import Api
    from client.app import MainWindow, ProcessingDialog, setup_font
    application = QApplication.instance() or QApplication([])
    setup_font(application)
    from PyQt6.QtGui import QRawFont
    assert QRawFont.fromFont(application.font()).supportsCharacter(ord("Ж"))

    class LocalApi(Api):
        def _req(self, method, path, **kwargs):
            headers = {"Authorization": "Bearer " + self.token} if self.token else {}
            response = client.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json() if response.headers.get("content-type", "").startswith("application/json") else response.content

    api = LocalApi()
    api.login("tech", "tech123")
    api.create_ticket(title="Проверка окна", description="Проверка MongoDB и графиков", category="network")
    window = MainWindow(api)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 6).text() == "Пользователь"
    dialog = ProcessingDialog(api, window)
    dialog.start("plot")
    deadline = time.monotonic() + 30
    while dialog.timer.isActive() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.05)
    assert dialog.status.text().startswith("Готово"), dialog.result.toPlainText()
    assert dialog.image.pixmap() is not None and not dialog.image.pixmap().isNull()
    dialog.resize(1100, 750)
    dialog.show()
    application.processEvents()
    dialog.grab().save(str(tmp_path / "processing.png"))
    dialog.close()
    window.close()
