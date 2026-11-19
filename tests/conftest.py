"""Интеграционные проверки используют отдельную настоящую MongoDB на каждый тест."""
import uuid
import pytest
from pymongo import MongoClient


@pytest.fixture
def test_mongo(monkeypatch):
    name = "itdesk_test_" + uuid.uuid4().hex
    monkeypatch.setenv("ITDESK_APP_DB", name)
    from server.db import settings
    uri, _ = settings()
    with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
        client.admin.command("ping")
        try:
            yield client[name]
        finally:
            # Удаляется только база, имя которой сгенерировано этой фикстурой.
            assert name.startswith("itdesk_test_") and len(name) == 44
            client.drop_database(name)
