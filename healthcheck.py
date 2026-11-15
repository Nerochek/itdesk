"""Проверка работоспособности (п.16): python healthcheck.py  (код возврата 0 = всё в порядке)."""
import sqlite3
import sys
from pathlib import Path

from itdesk_core import Api, ApiError, base_dir, db_path, load_config

REQUIRED = {"users", "sessions", "tickets", "comments", "history"}


def main() -> int:
    ok = True
    cfg_file = base_dir() / "config.ini"
    print(f"[{'OK' if cfg_file.exists() else '!!'}] Конфигурация: {cfg_file}"
          + ("" if cfg_file.exists() else " (не найден, используются значения по умолчанию)"))

    path = Path(db_path())
    if not path.exists():
        print(f"[!!] БД {path} ещё не создана: она появится при первом запуске сервера")
    else:
        try:
            with sqlite3.connect(path) as c:
                tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = REQUIRED - tables
            print(f"[{'OK' if not missing else 'FAIL'}] БД {path}"
                  + (f": нет таблиц {sorted(missing)}" if missing else f": таблицы на месте ({len(REQUIRED)})"))
            ok &= not missing
        except sqlite3.Error as e:
            print(f"[FAIL] БД {path} не открывается: {e}")
            ok = False

    url = load_config()["client"]["server_url"]
    try:
        info = Api().health()
        print(f"[OK] Сервер {url} отвечает, версия {info['version']}")
    except ApiError as e:
        print(f"[FAIL] Сервер {url}: {e}")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
