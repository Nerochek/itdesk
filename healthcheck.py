"""Проверка сервера и основной MongoDB: python healthcheck.py."""
from itdesk_core import Api, ApiError
from server import db


def main():
    try:
        with db.conn() as database:
            database.client.admin.command("ping")
            print(f"[OK] MongoDB: {database.name}; заявок: {database.tickets.count_documents({})}")
        print("[OK] API:", Api().health())
        return 0
    except Exception as error:
        print("[FAIL]", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
