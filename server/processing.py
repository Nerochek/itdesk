"""Фоновые задачи над документами рабочего приложения, с изоляцией результатов."""
import json
import os
import subprocess
import sys
from threading import Thread
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from typing import Literal

from . import db
from analytics.pipeline import ROOT

router = APIRouter(prefix="/processing", tags=["Обработка заявок"])
RUNS = ROOT / "analytics_data" / "runs"


class JobIn(BaseModel):
    action: Literal["seed", "import", "clean", "spark", "hadoop", "optimize", "plot", "all"]


def execute_job(identifier, action, uri, name):
    directory = RUNS / identifier
    env = dict(os.environ, ITDESK_MONGO_URI=uri, ITDESK_APP_DB=name,
               ITDESK_ANALYTICS_DIR=str(directory), PYTHONUTF8="1")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([sys.executable, "-m", "analytics.application", action],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        (directory / "job.log").write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] or f"Код завершения {result.returncode}")
        payload = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        update = {"status": "done", "result": payload}
    except Exception as error:
        if directory.is_dir() and not (directory / "job.log").exists():
            (directory / "job.log").write_text(str(error), encoding="utf-8")
        update = {"status": "failed", "error": str(error)}
    with db.conn() as database:
        database.processing_jobs.update_one({"_id": identifier}, {"$set": update})
        database.processing_jobs.delete_one({"_id": "active", "job_id": identifier})


@router.post("/jobs", status_code=202)
def start_job(data: JobIn):
    identifier = uuid.uuid4().hex
    with db.conn() as database:
        try:
            database.processing_jobs.insert_one({"_id": "active", "job_id": identifier})
        except DuplicateKeyError:
            raise HTTPException(409, "Уже выполняется обработка. Дождитесь завершения.")
        database.processing_jobs.insert_one({"_id": identifier, "action": data.action, "status": "running"})
    uri, name = db.settings()
    Thread(target=execute_job, args=(identifier, data.action, uri, name), daemon=True).start()
    return {"id": identifier, "status": "running"}


def get_job(identifier):
    if len(identifier) != 32 or any(char not in "0123456789abcdef" for char in identifier):
        raise HTTPException(404, "Результат не найден")
    with db.conn() as database:
        job = database.processing_jobs.find_one({"_id": identifier})
    if not job:
        raise HTTPException(404, "Результат не найден")
    job["id"] = job.pop("_id")
    return job


@router.get("/jobs/{identifier}")
def job_status(identifier: str):
    return get_job(identifier)


@router.get("/jobs/{identifier}/files/{filename}")
def job_file(identifier: str, filename: str):
    get_job(identifier)
    allowed = {"dashboard.png", "dashboard.pdf", "summary.csv", "clean.csv", "clean_receipt.json",
               "spark_sql.json", "spark_plans.txt", "mongo_explain.json", "hadoop_status.json",
               "hadoop_result.json", "job.log", "result.json"}
    path = RUNS / identifier / filename
    if filename not in allowed or not path.is_file():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path)
