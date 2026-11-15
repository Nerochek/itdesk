# ITDesk — центр заявок ИТ-поддержки университета

Десктопное приложение (PyQt6) + локальный REST API (FastAPI) + SQLite.

## п.4 Архитектура и технологии
Клиент (PyQt6) → библиотека `itdesk_core` → HTTP/JSON → сервер (FastAPI) → SQLite.
- `server/` — API, БД, защита; `client/` — GUI; `itdesk_core/` — библиотека; `tests/` — pytest.
- Роли: `user` (подаёт заявки, видит только свои), `tech` и `admin` (видят все, меняют статусы, статистика, экспорт).

## п.12 Библиотека `itdesk_core`
Отдельный пакет с повторно используемым кодом: `Api`/`ApiError` (клиент REST API), справочники
`STATUS`/`PRIORITY`/`CATEGORY`, функции `format_ticket_html`, `format_stats`, `label`.
GUI подключает его через `from itdesk_core import ...`. Установка как библиотеки: `pip install -e .`
(тогда `itdesk_core` можно подключить в любом другом проекте).

## п.5 Git / GitHub
```
git init && git add . && git commit -m "Initial commit: ITDesk"
git branch -M main && git remote add origin <URL> && git push -u origin main
```
Ветки: `main` (стабильная), `develop`, `feature/<название>`. Слияние через Pull Request.

## п.6 Запуск
```
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
pip install -e .               # подключить библиотеку itdesk_core
python run_server.py           # терминал 1
python run_client.py           # терминал 2
pytest                         # тесты
```
Тестовые учётки: `admin/admin123`, `tech/tech123` (смените перед реальным использованием).
Остальные регистрируются в окне входа.
