"""Задачи кнопок приложения. Источник — рабочая MongoDB ITDesk."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace
from urllib.request import Request, urlopen

from server import db
from . import pipeline


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_document(database, source, source_id, title, status, category="other", priority="medium"):
    query = {"source": source, "source_id": source_id}
    if database.tickets.find_one(query, {"_id": 1}):
        return False
    identifier = db.next_id(database, "tickets")
    # Повторный импорт не сбрасывает статусы и комментарии, изменённые пользователем.
    result = database.tickets.update_one(query, {"$setOnInsert": {
        **query, "id": identifier, "title": title[:120], "description": "Учебный пример для демонстрации",
        "category": category, "priority": priority, "status": status, "room": "",
        "author_id": None, "author": "Учебные данные" if source == "demo" else "Внешний API",
        "assignee_id": None, "assignee": None, "created_at": stamp() if source == "demo" else None,
        "updated_at": stamp(), "comments": [], "history": []}}, upsert=True)
    return result.upserted_id is not None


def populate():
    rng = random.Random(42)
    count = 0
    with db.conn() as database:
        for number in range(1, 1001):
            count += add_document(database, "demo", number, f"Учебная заявка {number}",
                rng.choice(pipeline.STATUSES), rng.choice(pipeline.CATEGORIES), rng.choice(pipeline.PRIORITIES))
    return f"Добавлено {count} учебных заявок. Они помечены источником demo и видны в общем списке сотрудников."


def import_api():
    url = "https://jsonplaceholder.typicode.com/todos"
    with urlopen(Request(url, headers={"User-Agent": "ITDesk/1.0"}), timeout=30) as response:
        rows = json.load(response)
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get("id"), int)
            and isinstance(row.get("title"), str) and isinstance(row.get("completed"), bool) for row in rows):
        raise ValueError("API вернул неожиданный формат")
    count = 0
    with db.conn() as database:
        for row in rows:
            database.external_raw.replace_one({"_id": f"todo:{row['id']}"},
                {"_id": f"todo:{row['id']}", "url": url, "payload": row}, upsert=True)
            count += add_document(database, "jsonplaceholder", row["id"], row["title"],
                                  "resolved" if row["completed"] else "new")
    return f"Получено {len(rows)} учебных todo из API, новых заявок: {count}. Источник jsonplaceholder; дата создания неизвестна."


def snapshot():
    fields = {name: 1 for name in ("source", "source_id", "title", "category", "priority", "status", "created_at")}
    with db.conn() as database:
        rows = list(database.tickets.find({}, {**fields, "_id": 0}))
    if not rows:
        raise ValueError("Заявок пока нет. Создайте заявку или нажмите «Учебные заявки».")
    pipeline.write_jsonl(pipeline.DATA / "source.jsonl", rows)
    pipeline.clean(SimpleNamespace(input=pipeline.DATA / "source.jsonl", to_mongo=False))
    return rows


def optimize():
    with db.conn() as database:
        sample = database.tickets.find_one({}, {"status": 1, "category": 1})
        query = {key: sample[key] for key in ("status", "category")}
        index = database.tickets.create_index([("status", 1), ("category", 1)], name="status_category")
        def explain(hint):
            return database.command("explain", {"find": "tickets", "filter": query, "hint": hint}, verbosity="executionStats")
        before, after = explain({"$natural": 1}), explain(index)
        if before["executionStats"]["nReturned"] != after["executionStats"]["nReturned"]:
            raise ValueError("Результаты поиска не совпали")
        pipeline.save_json(pipeline.DATA / "mongo_explain.json", {"query": query, "before": before, "after": after})
        return (f"Поиск MongoDB: найдено {after['executionStats']['nReturned']}; просмотрено документов "
                f"без индекса {before['executionStats']['totalDocsExamined']}, с индексом {after['executionStats']['totalDocsExamined']}.")


def hadoop():
    result = subprocess.run([sys.executable, "-m", "analytics.mapreduce.run"], check=False)
    if result.returncode:
        raise RuntimeError("Hadoop завершился с ошибкой. Подробности в журнале задачи.")
    output = pipeline.DATA / "hadoop-output"
    counts = {}
    for path in output.glob("part-*"):
        for line in path.read_text(encoding="utf-8").splitlines():
            key, value = line.split("\t")
            counts[key] = int(value)
    expected = dict(Counter(row["category"] for row in pipeline.read_jsonl(pipeline.DATA / "clean.jsonl")
                            if row["status"] in ("new", "in_progress")))
    if counts != expected or not (output / "_SUCCESS").exists():
        raise ValueError("Hadoop не подтвердил правильный результат")
    pipeline.save_json(pipeline.DATA / "hadoop_result.json", {"counts": counts, "equal": True, "engine": "Apache Hadoop Streaming"})
    return "Настоящий Hadoop Streaming выполнен; _SUCCESS получен, подсчёт совпал с контрольным."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "import", "clean", "spark", "hadoop", "optimize", "plot", "all"))
    args = parser.parse_args()
    from run_analytics import configure
    configure()
    pipeline.DATA.mkdir(parents=True, exist_ok=True)
    messages = []
    if args.action == "seed":
        messages.append(populate())
    elif args.action == "import":
        messages.append(import_api())
    else:
        rows = snapshot()
        messages.append(f"Снимок рабочей MongoDB: {len(rows)} заявок. Очистка Pandas завершена.")
        actions = ("spark", "hadoop", "optimize", "plot") if args.action == "all" else (args.action,)
        for action in actions:
            if action == "spark":
                pipeline.spark(SimpleNamespace(input=pipeline.DATA / "clean.jsonl"))
                messages.append("Spark RDD, DataFrame и SQL: результаты совпали. Планы и измерения сохранены.")
            elif action == "hadoop":
                messages.append(hadoop())
            elif action == "optimize":
                messages.append(optimize())
            elif action == "plot":
                pipeline.plot(SimpleNamespace(input=pipeline.DATA / "clean.jsonl"))
                messages.append("Графики построены по текущим заявкам приложения.")
    pipeline.save_json(pipeline.DATA / "result.json", {"messages": messages,
        "files": sorted(path.name for path in pipeline.DATA.iterdir() if path.is_file() and path.suffix in (".png", ".pdf", ".csv", ".json", ".txt"))})


if __name__ == "__main__":
    main()
