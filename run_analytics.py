"""Удобный запуск аналитики: python run_analytics.py --help."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from analytics.pipeline import ROOT, DATA


def configure():
    os.chdir(ROOT)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    if not os.getenv("JAVA_HOME"):
        candidates = sorted((ROOT / ".tools/java").glob("jdk*"))
        if candidates:
            os.environ["JAVA_HOME"] = str(candidates[-1])
    hadoop = ROOT / ".tools/hadoop-3.5.0"
    if not os.getenv("HADOOP_HOME") and hadoop.exists():
        os.environ["HADOOP_HOME"] = str(hadoop)
    for variable in ("JAVA_HOME", "HADOOP_HOME"):
        if os.getenv(variable):
            os.environ["PATH"] = str(Path(os.environ[variable]) / "bin") + os.pathsep + os.environ["PATH"]
    # Hadoop mapper/reducer должны найти Python именно текущего окружения.
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]


def run(*args):
    subprocess.run([sys.executable, "-m", *map(str, args)], check=True)


def start_mongo():
    from pymongo import MongoClient
    uri = os.environ.get("ITDESK_MONGO_URI", "mongodb://127.0.0.1:27017")
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=1000) as client:
            client.admin.command("ping")
        print("MongoDB уже доступна")
        return
    except Exception:
        if uri != "mongodb://127.0.0.1:27017":
            raise RuntimeError("Настроена внешняя MongoDB. Проверьте её доступность.")
    candidates = list((ROOT / ".tools/mongodb").rglob("mongod.exe"))
    executable = shutil.which("mongod") or (str(candidates[0]) if candidates else None)
    if not executable:
        raise RuntimeError("MongoDB не найдена: установите MongoDB или укажите ITDESK_MONGO_URI")
    data = ROOT / ".tools/mongodb-data"
    data.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(exist_ok=True)
    child = subprocess.Popen([executable, "--dbpath", str(data), "--bind_ip", "127.0.0.1",
        "--port", "27017", "--logpath", str(DATA / "mongodb.log"), "--logappend"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with MongoClient(uri, serverSelectionTimeoutMS=15000) as client:
        client.admin.command("ping")
    print("MongoDB запущена, PID:", child.pid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("doctor", "demo", "start-mongo", "full", "spark", "hadoop"))
    args = parser.parse_args()
    configure()
    try:
        if args.action == "start-mongo":
            start_mongo()
        elif args.action == "demo":
            run("analytics.pipeline", "seed")
            run("analytics.pipeline", "clean", "--input", DATA / "demo.jsonl")
            run("analytics.mapreduce.local_check")
            run("analytics.pipeline", "plot")
        elif args.action == "full":
            start_mongo()
            from server import db
            db.init_db()
            run("analytics.application", "all")
            print("Обработка заявок MongoDB завершена, включая настоящий Hadoop.")
        elif args.action == "hadoop":
            run("analytics.mapreduce.run")
        else:
            run("analytics.pipeline", args.action)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Ошибка: {error}\n")


if __name__ == "__main__":
    main()
