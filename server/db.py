"""Основное хранилище ITDesk: MongoDB."""
import os
from contextlib import contextmanager
from pymongo import MongoClient, ReturnDocument
from itdesk_core.config import load_config


def settings():
    config = load_config()["mongodb"]
    return (os.getenv("ITDESK_MONGO_URI", config["uri"]),
            os.getenv("ITDESK_APP_DB", config["database"]))


@contextmanager
def conn():
    uri, name = settings()
    with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
        yield client[name]


def next_id(database, name):
    row = database.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"value": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER)
    return row["value"]


def init_db():
    from .security import hash_password
    with conn() as database:
        database.client.admin.command("ping")
        for name in ("users", "sessions", "tickets", "external_raw", "processing_jobs", "counters"):
            if name not in database.list_collection_names():
                database.create_collection(name)
        database.users.create_index("username", unique=True)
        database.users.create_index("id", unique=True)
        database.sessions.create_index("token", unique=True)
        database.tickets.create_index("id", unique=True)
        database.tickets.create_index([("source", 1), ("source_id", 1)], unique=True,
                                     partialFilterExpression={"source_id": {"$exists": True}})
        database.tickets.create_index([("status", 1), ("category", 1)], name="status_category")
        database.tickets.create_index([("author_id", 1), ("id", -1)])
        for name, password, role in (("admin", "admin123", "admin"), ("tech", "tech123", "tech")):
            if not database.users.find_one({"username": name}):
                database.users.update_one({"username": name}, {"$setOnInsert": {
                    "id": next_id(database, "users"), "username": name,
                    "password_hash": hash_password(password), "role": role}}, upsert=True)
