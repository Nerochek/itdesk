"""Однократный перенос старой SQLite с сохранением ID и исходного файла."""
from pathlib import Path
import sqlite3
from . import db
from itdesk_core.config import db_path


def migrate_sqlite(path=None):
    path = Path(path or db_path()).resolve()
    if not path.is_file():
        return "Старая SQLite не найдена; используется MongoDB."
    with db.conn() as database:
        if database.migrations.find_one({"_id": "sqlite-v1"}):
            return "Перенос SQLite уже выполнен."
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            users = [dict(row) for row in connection.execute("SELECT * FROM users")]
            tickets = [dict(row) for row in connection.execute("SELECT * FROM tickets")]
            # При несовместимом наполнении не перезаписываем рабочую MongoDB.
            for user in users:
                conflicts = list(database.users.find({"$or": [{"id": user["id"]}, {"username": user["username"]}]}))
                if any(row["id"] != user["id"] or row["username"] != user["username"] for row in conflicts):
                    raise ValueError("Невозможно автоматически перенести SQLite: конфликт пользователей MongoDB.")
            for ticket in tickets:
                existing = database.tickets.find_one({"id": ticket["id"]})
                if existing and existing.get("legacy_sqlite") != str(path):
                    raise ValueError("Невозможно автоматически перенести SQLite: конфликт ID заявок MongoDB.")
            names = {row["id"]: row["username"] for row in users}
            for user in users:
                database.users.update_one({"id": user["id"]}, {"$setOnInsert": user}, upsert=True)
                # Сохраняем исходные пароли и роли только при первой миграции в пустую систему.
                # Существующие пользователи MongoDB не изменяются.
            for ticket in tickets:
                identifier = ticket["id"]
                ticket.update(source="itdesk", source_id=identifier, author=names.get(ticket["author_id"], ""),
                    assignee=names.get(ticket["assignee_id"]), legacy_sqlite=str(path))
                ticket["comments"] = [{"username": names.get(row["user_id"], ""), "text": row["text"],
                    "created_at": row["created_at"]} for row in connection.execute(
                        "SELECT * FROM comments WHERE ticket_id=? ORDER BY id", (identifier,))]
                ticket["history"] = [{"username": names.get(row["user_id"], ""), "action": row["action"],
                    "created_at": row["created_at"]} for row in connection.execute(
                        "SELECT * FROM history WHERE ticket_id=? ORDER BY id", (identifier,))]
                database.tickets.update_one({"id": identifier}, {"$setOnInsert": ticket}, upsert=True)
            for collection in ("users", "tickets"):
                highest = database[collection].find_one(sort=[("id", -1)])
                if highest:
                    database.counters.update_one({"_id": collection}, {"$max": {"value": highest["id"]}}, upsert=True)
            database.migrations.insert_one({"_id": "sqlite-v1", "source": str(path), "users": len(users), "tickets": len(tickets)})
    return f"Перенесено из SQLite: пользователей {len(users)}, заявок {len(tickets)}. Исходный файл сохранён."
