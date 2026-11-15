"""Загрузка конфигурации (п.16). Работает и из исходников, и из собранного .exe."""
import configparser
import os
import sys
from functools import lru_cache
from pathlib import Path

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": "8000", "db_path": "itdesk.db"},
    "client": {"server_url": "http://127.0.0.1:8000"},
}


def base_dir() -> Path:
    """Папка программы: рядом с .exe или корень проекта."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=8)
def _load(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(DEFAULTS)
    cfg.read(path, encoding="utf-8")
    return cfg


def load_config(path=None) -> configparser.ConfigParser:
    """Значения по умолчанию + config.ini (путь можно задать переменной ITDESK_CONFIG)."""
    return _load(str(path or os.environ.get("ITDESK_CONFIG") or base_dir() / "config.ini"))


def db_path() -> str:
    """Путь к файлу БД: переменная ITDESK_DB (для тестов) приоритетнее config.ini."""
    env = os.environ.get("ITDESK_DB")
    if env:
        return env
    p = Path(load_config()["server"]["db_path"])
    return str(p if p.is_absolute() else base_dir() / p)
