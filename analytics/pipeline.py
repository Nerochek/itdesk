"""Пункты 6–15. Запуск: python -m analytics.pipeline --help."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import statistics
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "analytics_data"
CATEGORIES = ("hardware", "network", "software", "projector", "account", "other")
STATUSES = ("new", "in_progress", "resolved", "closed")
PRIORITIES = ("low", "medium", "high")


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"Строка {number}: ожидается JSON-объект")
                yield row


def mongo():
    from pymongo import MongoClient
    client = MongoClient(os.getenv("ITDESK_MONGO_URI", "mongodb://127.0.0.1:27017"),
                         serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        raise
    return client


def database(client):
    return client[os.getenv("ITDESK_MONGO_DB", "itdesk_analytics")]


def init_mongo(_):
    with mongo() as client:
        db = database(client)
        for name in ("tickets_raw", "external_raw", "tickets_clean", "crud_demo"):
            if name not in db.list_collection_names():
                db.create_collection(name)
        db.tickets_raw.create_index([("source", 1), ("source_id", 1)], unique=True)
        db.external_raw.create_index([("source", 1), ("source_id", 1)], unique=True)
        db.tickets_clean.create_index([("source", 1), ("source_id", 1)], unique=True)
        print("Созданы БД, коллекции и индексы:", db.name, db.list_collection_names())


def upsert_rows(collection, rows):
    from pymongo import ReplaceOne
    count = 0
    batch = []
    for row in rows:
        row = dict(row)
        row.pop("_id", None)
        batch.append(ReplaceOne({"source": row["source"], "source_id": row["source_id"]}, row, upsert=True))
        if len(batch) == 1000:
            collection.bulk_write(batch, ordered=False)
            count += len(batch)
            batch = []
    if batch:
        collection.bulk_write(batch, ordered=False)
        count += len(batch)
    return count


def seed(args):
    rng = random.Random(42)
    def rows():
        for i in range(args.count):
            yield {"source": "demo", "source_id": i + 1, "title": f"Учебная заявка {i + 1}",
                   "category": rng.choice(CATEGORIES), "priority": rng.choice(PRIORITIES),
                   "status": rng.choice(STATUSES), "created_at": f"2026-11-{1 + i % 20:02d} 09:00:00"}
    path = DATA / "demo.jsonl"
    write_jsonl(path, rows())
    print("Учебные синтетические данные:", path, args.count)


def load(args):
    with mongo() as client:
        print("Загружено:", upsert_rows(database(client).tickets_raw, read_jsonl(args.input)))


def export_itdesk(args):
    path = Path(args.database).resolve()
    if not path.is_file():
        raise ValueError(f"База ITDesk не найдена: {path}")
    # Чтение исходной SQLite только для экспорта, без персональных данных.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = ({"source": "itdesk", "source_id": row["id"], **dict(row)} for row in connection.execute(
            "SELECT id,title,category,priority,status,created_at FROM tickets ORDER BY id"))
        write_jsonl(args.output, rows)
    print("Выгрузка ITDesk:", args.output)


def crud(_):
    with mongo() as client:
        col = database(client).crud_demo
        # Удаляется только созданный этим запуском документ в отдельной коллекции.
        identifier = col.insert_one({"title": "Проверка CRUD", "status": "new"}).inserted_id
        try:
            created = col.find_one({"_id": identifier})
            col.update_one({"_id": identifier}, {"$set": {"status": "resolved"}})
            updated = col.find_one({"_id": identifier})
        finally:
            deleted = col.delete_one({"_id": identifier}).deleted_count
        result = {"created": created, "updated": updated, "deleted_count": deleted}
        save_json(DATA / "crud_result.json", result)
        print(json.dumps(result, ensure_ascii=False, default=str))


def search(args):
    with mongo() as client:
        query = {"status": args.status}
        if args.category:
            query["category"] = args.category
        rows = list(database(client).tickets_raw.find(query, {"_id": 0}).sort("source_id", 1).limit(args.limit))
        save_json(DATA / "search_result.json", rows)
        print(json.dumps(rows, ensure_ascii=False, indent=2))


def fetch(args):
    # Публичный учебный API: сохраняем исходные данные и преобразованные заявки.
    url = "https://jsonplaceholder.typicode.com/todos"
    request = Request(url, headers={"User-Agent": "ITDesk-Practice/1.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, list) or not all(isinstance(row, dict) and
            isinstance(row.get("id"), int) and isinstance(row.get("title"), str) and
            isinstance(row.get("completed"), bool) for row in payload):
        raise ValueError("Внешний API вернул неожиданный формат")
    raw = [{"source": "jsonplaceholder", "source_id": row["id"], "payload": row} for row in payload]
    tickets = [{"source": "jsonplaceholder", "source_id": row["id"], "title": row["title"],
                "status": "resolved" if row["completed"] else "new", "category": "other",
                "priority": "medium", "created_at": None} for row in payload]
    with mongo() as client:
        db = database(client)
        upsert_rows(db.external_raw, raw)
        count = upsert_rows(db.tickets_raw, tickets)
    save_json(DATA / "external_api_receipt.json", {"url": url, "count": count,
              "note": "Учебные todo, не реальные заявки ITDesk. Дата создания неизвестна."})
    print("Загружено из внешнего API:", count)


def clean_frame(rows):
    import pandas as pd
    columns = ["source", "source_id", "title", "category", "priority", "status", "created_at"]
    frame = pd.DataFrame(rows).reindex(columns=columns)
    before = len(frame)
    frame["source_id"] = pd.to_numeric(frame["source_id"], errors="coerce")
    valid_id = frame["source_id"].notna() & frame["source_id"].gt(0) & frame["source_id"].mod(1).eq(0)
    frame = frame.loc[valid_id].copy()
    frame["source_id"] = frame["source_id"].astype("int64")
    for column in ("source", "title", "category", "priority", "status"):
        frame[column] = frame[column].astype("string").fillna("").astype(str).str.strip()
    frame = frame.loc[frame["source"].ne("") & frame["title"].ne("")].copy()
    for column, allowed, fallback in (("category", CATEGORIES, "other"),
            ("priority", PRIORITIES, "medium"), ("status", STATUSES, "new")):
        frame[column] = frame[column].str.lower()
        frame.loc[~frame[column].isin(allowed), column] = fallback
    frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    frame = frame.drop_duplicates(["source", "source_id"], keep="last")
    frame = frame.sort_values(["status", "category", "source", "source_id"]).reset_index(drop=True)
    frame = frame.astype(object).where(frame.notna(), None)
    return frame, {"input_rows": before, "output_rows": len(frame), "removed_rows": before - len(frame)}


def clean(args):
    if args.input:
        rows = list(read_jsonl(args.input))
    else:
        with mongo() as client:
            rows = list(database(client).tickets_raw.find({}, {"_id": 0}))
    frame, receipt = clean_frame(rows)
    DATA.mkdir(exist_ok=True)
    write_jsonl(DATA / "clean.jsonl", frame.to_dict("records"))
    frame.to_csv(DATA / "clean.csv", index=False, encoding="utf-8-sig")
    frame.loc[frame["status"].isin(["new", "in_progress"])].to_csv(
        DATA / "active.csv", index=False, encoding="utf-8-sig")
    if args.to_mongo:
        with mongo() as client:
            upsert_rows(database(client).tickets_clean, frame.to_dict("records"))
    save_json(DATA / "clean_receipt.json", receipt)
    print(receipt)


def spark(args):
    from pyspark.sql import SparkSession, functions as F, types as T
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    session = SparkSession.builder.master("local[2]").appName("ITDeskPractice").getOrCreate()
    try:
        schema = T.StructType([T.StructField("source_id", T.LongType()), *[
            T.StructField(name, T.StringType()) for name in
            ("source", "title", "category", "priority", "status", "created_at")]])
        frame = session.read.schema(schema).json(str(Path(args.input).resolve()))
        # Пункт 12: реальные RDD filter/map/reduceByKey и DataFrame filter/groupBy.
        counts = dict(frame.rdd.filter(lambda row: row.status in ("new", "in_progress"))
                      .map(lambda row: (row.category, 1)).reduceByKey(lambda a, b: a + b).collect())
        save_json(DATA / "spark_rdd.json", counts)
        aggregate = frame.filter(F.col("status").isin("new", "in_progress")).groupBy("category").count().orderBy("category").collect()
        # На драйвер передаётся только агрегат (не более 6 категорий).
        dataframe_counts = {row.category: row["count"] for row in aggregate}
        if dataframe_counts != counts:
            raise ValueError("RDD и DataFrame не совпали")
        save_json(DATA / "spark_dataframe.json", dataframe_counts)
        frame.createOrReplaceTempView("tickets")
        # Пункт 13: эквивалентные SQL, планы и измерение после прогрева.
        baseline = session.sql("SELECT category, COUNT(*) AS total FROM tickets WHERE status IN ('new','in_progress') GROUP BY category ORDER BY category")
        active = frame.select("category", "status").filter(F.col("status").isin("new", "in_progress")).select("category").cache()
        cache_start = time.perf_counter()
        active.count()
        cache_build_seconds = time.perf_counter() - cache_start
        active.createOrReplaceTempView("active_tickets")
        optimized = session.sql("SELECT category, COUNT(*) AS total FROM active_tickets GROUP BY category ORDER BY category")
        def measure(query):
            samples = []
            result = query.collect()
            for _ in range(3):
                start = time.perf_counter()
                query.collect()
                samples.append(time.perf_counter() - start)
            return result, statistics.median(samples)
        first, before = measure(baseline)
        second, after = measure(optimized)
        if first != second or dict((r.category, r.total) for r in second) != counts:
            raise ValueError("Результаты RDD/DataFrame SQL не совпали")
        save_json(DATA / "spark_sql.json", {"rows": [r.asDict() for r in second],
                  "baseline_seconds": before, "cached_seconds": after, "cache_build_seconds": cache_build_seconds,
                  "note": "Медиана 3 повторов после прогрева. Время построения кэша не включено. Ускорение не гарантируется."})
        (DATA / "spark_plans.txt").write_text("BEFORE\n" + baseline._jdf.queryExecution().toString() +
            "\nAFTER\n" + optimized._jdf.queryExecution().toString(), encoding="utf-8")
        active.unpersist()
        print("Spark RDD/DataFrame/SQL: результаты совпадают")
    finally:
        session.stop()


def benchmark(args):
    with mongo() as client:
        col = database(client).tickets_raw
        if col.count_documents({}) == 0:
            raise ValueError("Сначала загрузите заявки в MongoDB")
        query = {"status": args.status, "category": args.category}
        # Сравниваем COLLSCAN и индекс без удаления существующих индексов.
        index = col.create_index([("status", 1), ("category", 1)], name="status_category_practice")
        def explain(hint):
            return col.database.command("explain", {"find": col.name, "filter": query, "hint": hint}, verbosity="executionStats")
        before, after = explain({"$natural": 1}), explain(index)
        if before["executionStats"]["nReturned"] != after["executionStats"]["nReturned"]:
            raise ValueError("Результаты запросов не совпали")
        save_json(DATA / "mongo_explain.json", {"query": query, "before": before, "after": after,
                  "note": "Сравните totalDocsExamined/totalKeysExamined. Малые данные не доказывают ускорение по времени."})
        print("Планы COLLSCAN и индексного поиска сохранены")


def plot(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    frame = pd.read_json(args.input, lines=True)
    if frame.empty:
        raise ValueError("Нет данных для графиков")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for axis, column, title in zip(axes, ("category", "status", "priority"),
                                 ("Категории", "Статусы", "Приоритеты")):
        counts = frame[column].value_counts().sort_index()
        counts.plot.bar(ax=axis, color="#3977ac")
        axis.set_title(title)
        axis.set_ylabel("Число заявок")
        axis.set_xlabel("")
        axis.tick_params(axis="x", rotation=40)
    fig.suptitle(f"ITDesk: {len(frame)} записей; источники: {", ".join(sorted(frame.source.unique()))}")
    fig.tight_layout()
    DATA.mkdir(exist_ok=True)
    fig.savefig(DATA / "dashboard.png", dpi=160)
    fig.savefig(DATA / "dashboard.pdf")
    plt.close(fig)
    frame.groupby(["source", "category", "status"]).size().rename("count").to_csv(
        DATA / "summary.csv", encoding="utf-8-sig")
    print("Графики:", DATA / "dashboard.png")


def doctor(_):
    result = {"python": sys.version, "libraries": {name: bool(importlib.util.find_spec(name))
        for name in ("pymongo", "pandas", "pyspark", "matplotlib")},
        "commands": {name: shutil.which(name) for name in ("mongod", "java", "hadoop")},
        "JAVA_HOME": os.getenv("JAVA_HOME"), "HADOOP_HOME": os.getenv("HADOOP_HOME")}
    try:
        with mongo() as client:
            result["mongo_ping"] = client.admin.command("ping")["ok"]
    except Exception as error:
        result["mongo_error"] = str(error)
    save_json(DATA / "environment.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    def command(name, function):
        sub = commands.add_parser(name, help=function.__name__)
        sub.set_defaults(function=function)
        return sub
    command("doctor", doctor)
    command("init", init_mongo)
    sub = command("seed", seed)
    sub.add_argument("--count", type=int, default=10000)
    sub = command("load", load)
    sub.add_argument("--input", type=Path, default=DATA / "demo.jsonl")
    sub = command("export-itdesk", export_itdesk)
    sub.add_argument("--database", type=Path, default=ROOT / "itdesk.db")
    sub.add_argument("--output", type=Path, default=DATA / "itdesk.jsonl")
    command("crud", crud)
    sub = command("search", search)
    sub.add_argument("--status", choices=STATUSES, default="new")
    sub.add_argument("--category", choices=CATEGORIES)
    sub.add_argument("--limit", type=int, default=20)
    command("fetch", fetch)
    sub = command("clean", clean)
    sub.add_argument("--input", type=Path, help="Без параметра: чтение MongoDB")
    sub.add_argument("--to-mongo", action="store_true")
    sub = command("spark", spark)
    sub.add_argument("--input", type=Path, default=DATA / "clean.jsonl")
    sub = command("benchmark", benchmark)
    sub.add_argument("--status", choices=STATUSES, default="new")
    sub.add_argument("--category", choices=CATEGORIES, default="network")
    sub = command("plot", plot)
    sub.add_argument("--input", type=Path, default=DATA / "clean.jsonl")
    args = parser.parse_args()
    if getattr(args, "count", 1) < 1 or getattr(args, "limit", 1) < 1:
        parser.error("count и limit должны быть положительными")
    try:
        args.function(args)
    except Exception as error:
        parser.exit(1, f"Ошибка ({type(error).__name__}): {error}\n")


if __name__ == "__main__":
    main()
