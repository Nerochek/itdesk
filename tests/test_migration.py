"""Миграция сохраняет данные, не перезаписывает изменения и не меняет SQLite."""
import sqlite3
import pytest
from server.migrate import migrate_sqlite
from server import db


def legacy(path):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE users(id INTEGER, username TEXT, password_hash TEXT, role TEXT);
            INSERT INTO users VALUES(10,'old_user','original_hash','user');
            CREATE TABLE tickets(id INTEGER,title TEXT,description TEXT,category TEXT,priority TEXT,
                room TEXT,status TEXT,author_id INTEGER,assignee_id INTEGER,created_at TEXT,updated_at TEXT);
            INSERT INTO tickets VALUES(20,'Old ticket','Description','other','low','','new',10,NULL,'2026-11-01','2026-11-01');
            CREATE TABLE comments(id INTEGER,ticket_id INTEGER,user_id INTEGER,text TEXT,created_at TEXT);
            INSERT INTO comments VALUES(1,20,10,'Old comment','2026-11-01');
            CREATE TABLE history(id INTEGER,ticket_id INTEGER,user_id INTEGER,action TEXT,created_at TEXT);
            INSERT INTO history VALUES(1,20,10,'Created','2026-11-01');
        """)


def test_migration_is_readonly_and_idempotent(test_mongo, tmp_path):
    path = tmp_path / "legacy.db"
    legacy(path)
    before = path.read_bytes()
    migrate_sqlite(path)
    db.init_db()
    assert test_mongo.users.find_one({"id": 10})["password_hash"] == "original_hash"
    ticket = test_mongo.tickets.find_one({"id": 20})
    assert ticket["author"] == "old_user" and len(ticket["comments"]) == 1 and len(ticket["history"]) == 1
    test_mongo.tickets.update_one({"id": 20}, {"$set": {"status": "closed"}})
    migrate_sqlite(path)
    assert test_mongo.tickets.find_one({"id": 20})["status"] == "closed"
    assert db.next_id(test_mongo, "tickets") > 20
    assert path.read_bytes() == before


def test_migration_rejects_conflicts_before_copy(test_mongo, tmp_path):
    path = tmp_path / "legacy.db"
    legacy(path)
    test_mongo.users.insert_one({"id": 10, "username": "different"})
    with pytest.raises(ValueError, match="конфликт"):
        migrate_sqlite(path)
    assert test_mongo.tickets.count_documents({}) == 0
