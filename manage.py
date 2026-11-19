"""Администрирование: смена пароля и роли (п.16, подготовка к эксплуатации).
  python manage.py passwd <логин>
  python manage.py role <логин> <user|tech|admin>
"""
import getpass
import sys

from server import db
from server.security import hash_password


def set_password(username: str, password: str) -> None:
    if len(password) < 6:
        raise ValueError("Пароль должен быть не короче 6 символов")
    with db.conn() as c:
        row = c.users.find_one({"username": username})
        if not row:
            raise ValueError(f"Пользователь {username!r} не найден")
        c.users.update_one({"id": row["id"]}, {"$set": {"password_hash": hash_password(password)}})
        c.sessions.delete_many({"user_id": row["id"]})


def set_role(username: str, role: str) -> None:
    if role not in ("user", "tech", "admin"):
        raise ValueError("Роль должна быть user, tech или admin")
    with db.conn() as c:
        user = c.users.find_one({"username": username})
        if not user:
            raise ValueError(f"Пользователь {username!r} не найден")
        c.users.update_one({"id": user["id"]}, {"$set": {"role": role}})
        c.sessions.delete_many({"user_id": user["id"]})


def main(argv):
    db.init_db()
    try:
        if len(argv) == 3 and argv[1] == "passwd":
            pw = getpass.getpass("Новый пароль: ")
            if pw != getpass.getpass("Повторите пароль: "):
                raise ValueError("Пароли не совпадают")
            set_password(argv[2], pw)
        elif len(argv) == 4 and argv[1] == "role":
            set_role(argv[2], argv[3])
        else:
            print(__doc__)
            return 1
    except ValueError as e:
        print("Ошибка:", e)
        return 1
    print("Готово.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
