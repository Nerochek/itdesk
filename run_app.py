"""Единый запуск MongoDB, сервера и окна ITDesk: python run_app.py."""
import json
import os
import subprocess
import sys
import time
from urllib.request import urlopen
from pathlib import Path

from run_analytics import configure, start_mongo
from itdesk_core.config import load_config
from server.migrate import migrate_sqlite
from server import db


def main():
    configure()
    start_mongo()
    # Миграция до init_db сохраняет исходные пароли admin и tech.
    print(migrate_sqlite())
    db.init_db()
    url = load_config()["client"]["server_url"] + "/health"
    child = None
    log_path = Path("analytics_data/server.log")
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        try:
            try:
                with urlopen(url, timeout=1) as response:
                    info = json.load(response)
                if info.get("storage") != "MongoDB":
                    raise RuntimeError("На порту приложения работает старый сервер. Остановите его (Ctrl+C) и повторите запуск.")
                if info.get("database") != db.settings()[1]:
                    raise RuntimeError("Уже работает сервер с другой базой. Закройте его перед запуском.")
            except (OSError, ValueError):
                child = subprocess.Popen([sys.executable, "run_server.py"], stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                deadline = time.monotonic() + 20
                while True:
                    if child.poll() is not None:
                        raise RuntimeError("Сервер не запустился. Подробности: analytics_data/server.log")
                    try:
                        with urlopen(url, timeout=1) as response:
                            info = json.load(response)
                        if info.get("storage") == "MongoDB":
                            break
                    except OSError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("Истекло время ожидания сервера. Проверьте server.log.")
                    time.sleep(0.2)
            return subprocess.call([sys.executable, "run_client.py"])
        finally:
            if child is not None:
                child.terminate()
                child.wait(timeout=15)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Не удалось запустить ITDesk:", error)
        raise SystemExit(1)
