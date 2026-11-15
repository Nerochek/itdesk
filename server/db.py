"""Слой работы с БД SQLite (п.16)."""
import sqlite3
from contextlib import contextmanager

from itdesk_core.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user');
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id));
CREATE TABLE IF NOT EXISTS tickets(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
  category TEXT NOT NULL, priority TEXT NOT NULL, room TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',
  author_id INTEGER NOT NULL REFERENCES users(id),
  assignee_id INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments(
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  user_id INTEGER NOT NULL REFERENCES users(id), text TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  user_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_author ON tickets(author_id);
"""


@contextmanager
def conn():
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    from .security import hash_password
    with conn() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM users").fetchone():
            for name, pw, role in [("admin", "admin123", "admin"), ("tech", "tech123", "tech")]:
                c.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                          (name, hash_password(pw), role))
