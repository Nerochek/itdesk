"""REST API ITDesk: все рабочие документы хранятся в MongoDB."""
import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from itdesk_core import __version__
from . import db
from .security import hash_password, new_token, verify_password

Status = Literal["new", "in_progress", "resolved", "closed"]
Priority = Literal["low", "medium", "high"]
Category = Literal["hardware", "network", "software", "projector", "account", "other"]


@asynccontextmanager
async def lifespan(_):
    db.init_db()
    # Desktop-режим: один процесс API на базу. После перезапуска не держим
    # блокировку задач, прерванных остановкой прежнего сервера.
    with db.conn() as database:
        database.processing_jobs.update_many({"status": "running"}, {"$set": {
            "status": "failed", "error": "Предыдущий сервер был остановлен. Запустите обработку повторно."}})
        database.processing_jobs.delete_one({"_id": "active"})
    yield


app = FastAPI(title="ITDesk MongoDB API", lifespan=lifespan)


@app.exception_handler(PyMongoError)
async def mongo_error(request, error):
    return JSONResponse(status_code=503, content={"detail": "MongoDB недоступна. Проверьте запуск базы данных."})


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Creds(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)


class TicketIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=2000)
    category: Category = "other"
    priority: Priority = "medium"
    room: str = Field(default="", max_length=30)


class TicketPatch(BaseModel):
    status: Optional[Status] = None
    assignee_id: Optional[int] = None


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def current_user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    with db.conn() as database:
        session = database.sessions.find_one({"token": token})
        user = database.users.find_one({"id": session["user_id"]}, {"_id": 0}) if session else None
    if not user:
        raise HTTPException(401, "Требуется авторизация")
    return user


def staff(user=Depends(current_user)):
    if user["role"] not in ("tech", "admin"):
        raise HTTPException(403, "Недостаточно прав")
    return user


@app.get("/health")
def health():
    with db.conn() as database:
        database.client.admin.command("ping")
        return {"status": "ok", "version": __version__, "storage": "MongoDB", "database": database.name}


@app.post("/auth/register", status_code=201)
def register(data: Creds):
    try:
        with db.conn() as database:
            database.users.insert_one({"id": db.next_id(database, "users"), "username": data.username,
                                       "password_hash": hash_password(data.password), "role": "user"})
    except DuplicateKeyError:
        raise HTTPException(409, "Пользователь уже существует")
    return {"ok": True}


@app.post("/auth/login")
def login(data: Creds):
    with db.conn() as database:
        user = database.users.find_one({"username": data.username})
        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = new_token()
        database.sessions.insert_one({"token": token, "user_id": user["id"]})
        return {"token": token, **{key: user[key] for key in ("id", "username", "role")}}


def ticket_query(user, tid=None):
    query = {"id": tid} if tid is not None else {}
    if user["role"] == "user":
        query["author_id"] = user["id"]
    return query


def find_ticket(database, tid, user):
    ticket = database.tickets.find_one(ticket_query(user, tid), {"_id": 0})
    if not ticket:
        raise HTTPException(404, "Заявка не найдена")
    return ticket


@app.get("/tickets")
def list_tickets(status: Optional[Status] = None, category: Optional[Category] = None,
                 q: str = "", u=Depends(current_user)):
    import re
    query = ticket_query(u)
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    if q:
        query["title"] = {"$regex": re.escape(q[:120]), "$options": "i"}
    with db.conn() as database:
        return list(database.tickets.find(query, {"_id": 0, "comments": 0, "history": 0}).sort("id", -1))


@app.post("/tickets", status_code=201)
def create_ticket(data: TicketIn, u=Depends(current_user)):
    if not data.title.strip() or not data.description.strip():
        raise HTTPException(422, "Заполните тему и описание")
    with db.conn() as database:
        identifier = db.next_id(database, "tickets")
        timestamp = now()
        database.tickets.insert_one({**data.model_dump(), "id": identifier,
            "source": "itdesk", "source_id": identifier, "status": "new", "author_id": u["id"],
            "author": u["username"], "assignee_id": None, "assignee": None,
            "created_at": timestamp, "updated_at": timestamp, "comments": [],
            "history": [{"username": u["username"], "action": "Заявка создана", "created_at": timestamp}]})
    return {"id": identifier}


@app.get("/tickets/{tid}")
def get_ticket(tid: int, u=Depends(current_user)):
    with db.conn() as database:
        return find_ticket(database, tid, u)


@app.get("/tickets/{tid}/document")
def get_document(tid: int, u=Depends(staff)):
    with db.conn() as database:
        ticket = find_ticket(database, tid, u)
        document = database.tickets.find_one({"id": ticket["id"]})
        document["_id"] = str(document["_id"])
        return {"database": database.name, "collection": "tickets", "document": document}


@app.patch("/tickets/{tid}")
def patch_ticket(tid: int, data: TicketPatch, u=Depends(staff)):
    with db.conn() as database:
        find_ticket(database, tid, u)
        changes, events = {"updated_at": now()}, []
        # Валидация полностью до записи: неверный исполнитель не изменит статус.
        if data.assignee_id is not None:
            assignee = database.users.find_one({"id": data.assignee_id, "role": {"$in": ["tech", "admin"]}})
            if not assignee:
                raise HTTPException(400, "Исполнитель должен быть сотрудником ИТ-отдела")
            changes.update(assignee_id=assignee["id"], assignee=assignee["username"])
            events.append("Назначен исполнитель")
        if data.status:
            changes["status"] = data.status
            events.append(f"Статус изменён на «{data.status}»")
        update = {"$set": changes}
        if events:
            update["$push"] = {"history": {"$each": [{"username": u["username"], "action": event,
                                                      "created_at": now()} for event in events]}}
        database.tickets.update_one({"id": tid}, update)
    return {"ok": True}


@app.delete("/tickets/{tid}")
def delete_ticket(tid: int, u=Depends(staff)):
    with db.conn() as database:
        find_ticket(database, tid, u)
        database.tickets.delete_one({"id": tid})
    return {"ok": True}


@app.post("/tickets/{tid}/comments", status_code=201)
def add_comment(tid: int, data: CommentIn, u=Depends(current_user)):
    with db.conn() as database:
        find_ticket(database, tid, u)
        database.tickets.update_one({"id": tid}, {"$push": {"comments": {
            "username": u["username"], "text": data.text, "created_at": now()}}})
    return {"ok": True}


@app.get("/stats")
def stats(_=Depends(staff)):
    with db.conn() as database:
        return {"by_" + column: {row["_id"]: row["count"] for row in database.tickets.aggregate([
            {"$group": {"_id": "$" + column, "count": {"$sum": 1}}}])}
            for column in ("status", "category", "priority")}


@app.get("/export.csv")
def export_csv(_=Depends(staff)):
    fields = ["id", "title", "category", "priority", "status", "author", "assignee", "created_at"]
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(fields)
    with db.conn() as database:
        for row in database.tickets.find().sort("id", 1):
            writer.writerow([row.get(field) or "" for field in fields])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8")


# Долгие вычисления выполняются фоновыми задачами, GUI опрашивает состояние.
from .processing import router
app.include_router(router, dependencies=[Depends(staff)])
