"""Корректная остановка только локальной MongoDB с данными этого проекта."""
import os
from pathlib import Path
from pymongo import MongoClient
from pymongo.errors import AutoReconnect
from analytics.pipeline import ROOT


def main():
    with MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000) as client:
        actual = Path(client.admin.command("getCmdLineOpts")["parsed"]["storage"]["dbPath"]).resolve()
        expected = (ROOT / ".tools/mongodb-data").resolve()
        if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
            raise RuntimeError("Отказ: MongoDB использует другую папку данных")
        try:
            client.admin.command("shutdown", force=False, timeoutSecs=15)
        except AutoReconnect:
            pass  # Сервер закрыл соединение при штатной остановке.
        print("Команда остановки MongoDB проекта отправлена")


if __name__ == "__main__":
    main()
