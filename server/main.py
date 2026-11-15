"""REST API (п.15). Запуск: python run_server.py"""
import csv
import io
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from itdesk_core import __version__

from . import db
from .security import hash_password, new_token, verify_password

Status = Literal["new", "in_progress", "resolved", "closed"]
Priority = Literal["low", "medium", "high"]
Category = Literal["hardware", "network", "software", "projector", "account", "other"]


@asynccontextmanager
async def lifespan(_):
    db.init_db()
    yield


app = FastAPI(title="ITDesk API", lifespan=lifespan)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    with db.conn() as c:
        row = c.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id "
                        "WHERE s.token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "Требуется авторизация")
    return dict(row)


def staff(u=Depends(current_user)):
    if u["role"] not in ("tech", "admin"):
        raise HTTPException(403, "Недостаточно прав")
    return u


@app.get("/health")
def health():
    """Проверка работоспособности: сервер запущен и БД доступна."""
    try:
        with db.conn() as c:
            c.execute("SELECT 1 FROM users LIMIT 1")
    except sqlite3.Error:
        raise HTTPException(503, "База данных недоступна")
    return {"status": "ok", "version": __version__}


@app.post("/auth/register", status_code=201)
def register(d: Creds):
    try:
        with db.conn() as c:
            c.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                      (d.username, hash_password(d.password)))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Пользователь уже существует")
    return {"ok": True}


@app.post("/auth/login")
def login(d: Creds):
    with db.conn() as c:
        u = c.execute("SELECT * FROM users WHERE username=?", (d.username,)).fetchone()
        if not u or not verify_password(d.password, u["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = new_token()
        c.execute("INSERT INTO sessions VALUES(?,?)", (token, u["id"]))
    return {"token": token, "username": u["username"], "role": u["role"], "id": u["id"]}


_SELECT = ("SELECT t.*, a.username AS author, e.username AS assignee FROM tickets t "
           "JOIN users a ON a.id=t.author_id LEFT JOIN users e ON e.id=t.assignee_id ")


@app.get("/tickets")
def list_tickets(status: Optional[Status] = None, u=Depends(current_user)):
    sql, args = _SELECT + "WHERE 1=1", []
    if u["role"] == "user":
        sql += " AND t.author_id=?"
        args.append(u["id"])
    if status:
        sql += " AND t.status=?"
        args.append(status)
    with db.conn() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY t.id DESC", args)]


@app.post("/tickets", status_code=201)
def create_ticket(d: TicketIn, u=Depends(current_user)):
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO tickets(title,description,category,priority,room,author_id,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (d.title, d.description, d.category, d.priority, d.room, u["id"], now(), now()))
        c.execute("INSERT INTO history(ticket_id,user_id,action,created_at) VALUES(?,?,?,?)",
                  (cur.lastrowid, u["id"], "Заявка создана", now()))
        return {"id": cur.lastrowid}


def _get_ticket(c, tid, u):
    t = c.execute(_SELECT + "WHERE t.id=?", (tid,)).fetchone()
    if not t or (u["role"] == "user" and t["author_id"] != u["id"]):
        raise HTTPException(404, "Заявка не найдена")
    return t


@app.get("/tickets/{tid}")
def get_ticket(tid: int, u=Depends(current_user)):
    with db.conn() as c:
        t = dict(_get_ticket(c, tid, u))
        t["comments"] = [dict(r) for r in c.execute(
            "SELECT c.text, c.created_at, us.username FROM comments c JOIN users us ON us.id=c.user_id "
            "WHERE ticket_id=? ORDER BY c.id", (tid,))]
        t["history"] = [dict(r) for r in c.execute(
            "SELECT h.action, h.created_at, us.username FROM history h JOIN users us ON us.id=h.user_id "
            "WHERE ticket_id=? ORDER BY h.id", (tid,))]
        return t


@app.patch("/tickets/{tid}")
def patch_ticket(tid: int, d: TicketPatch, u=Depends(staff)):
    with db.conn() as c:
        _get_ticket(c, tid, u)
        if d.status:
            c.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?", (d.status, now(), tid))
            c.execute("INSERT INTO history(ticket_id,user_id,action,created_at) VALUES(?,?,?,?)",
                      (tid, u["id"], f"Статус изменён на «{d.status}»", now()))
        if d.assignee_id is not None:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role IN ('tech','admin')",
                             (d.assignee_id,)).fetchone():
                raise HTTPException(400, "Исполнитель должен быть сотрудником ИТ-отдела")
            c.execute("UPDATE tickets SET assignee_id=?, updated_at=? WHERE id=?",
                      (d.assignee_id, now(), tid))
            c.execute("INSERT INTO history(ticket_id,user_id,action,created_at) VALUES(?,?,?,?)",
                      (tid, u["id"], "Назначен исполнитель", now()))
    return {"ok": True}


@app.post("/tickets/{tid}/comments", status_code=201)
def add_comment(tid: int, d: CommentIn, u=Depends(current_user)):
    with db.conn() as c:
        _get_ticket(c, tid, u)
        c.execute("INSERT INTO comments(ticket_id,user_id,text,created_at) VALUES(?,?,?,?)",
                  (tid, u["id"], d.text, now()))
    return {"ok": True}


@app.get("/stats")
def stats(_=Depends(staff)):
    with db.conn() as c:
        by = lambda col: {r[0]: r[1] for r in c.execute(
            f"SELECT {col}, COUNT(*) FROM tickets GROUP BY {col}")}
        return {"by_status": by("status"), "by_category": by("category"),
                "by_priority": by("priority")}


@app.get("/export.csv")
def export_csv(_=Depends(staff)):
    with db.conn() as c:
        rows = c.execute(_SELECT + "ORDER BY t.id").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "title", "category", "priority", "status", "author", "assignee", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["title"], r["category"], r["priority"], r["status"],
                    r["author"], r["assignee"] or "", r["created_at"]])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8")
