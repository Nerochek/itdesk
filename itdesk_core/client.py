"""Клиент REST API ITDesk (не зависит от GUI, можно использовать в любом проекте)."""
import requests

from .config import load_config


class ApiError(Exception):
    pass


class Api:
    def __init__(self, base=None):
        self.base = base or load_config()["client"]["server_url"]
        self.token, self.user = None, None

    def _req(self, method, path, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = requests.request(method, self.base + path, headers=headers, timeout=5, **kw)
        except requests.RequestException:
            raise ApiError("Нет связи с сервером. Запущен ли run_server.py?")
        is_json = r.headers.get("content-type", "").startswith("application/json")
        if r.status_code >= 400:
            detail = r.json().get("detail") if is_json else r.text
            raise ApiError(detail if isinstance(detail, str) else "Проверьте введённые данные")
        return r.json() if is_json else r.content

    def health(self):
        """Проверка доступности сервера и БД (без авторизации)."""
        return self._req("GET", "/health")

    def login(self, username, password):
        d = self._req("POST", "/auth/login", json={"username": username, "password": password})
        self.token, self.user = d["token"], d

    def register(self, username, password):
        self._req("POST", "/auth/register", json={"username": username, "password": password})

    def tickets(self, status=None):
        return self._req("GET", "/tickets", params={"status": status} if status else None)

    def ticket(self, tid):
        return self._req("GET", f"/tickets/{tid}")

    def create_ticket(self, **data):
        return self._req("POST", "/tickets", json=data)

    def update_ticket(self, tid, **data):
        return self._req("PATCH", f"/tickets/{tid}", json=data)

    def comment(self, tid, text):
        return self._req("POST", f"/tickets/{tid}/comments", json={"text": text})

    def stats(self):
        return self._req("GET", "/stats")

    def export_csv(self):
        return self._req("GET", "/export.csv")
