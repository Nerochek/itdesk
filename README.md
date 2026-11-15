# ITDesk — центр заявок ИТ-поддержки университета

Десктопное приложение (PyQt6) + локальный REST API (FastAPI) + SQLite.

## п.4 Архитектура и технологии
Клиент (PyQt6) → HTTP/JSON → сервер (FastAPI) → SQLite.
- `server/` — API, БД, защита; `client/` — GUI и библиотека `api.py`; `tests/` — pytest.
- Роли: `user` (подаёт заявки, видит только свои), `tech` и `admin` (видят все, меняют статусы, статистика, экспорт).

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
python run_server.py           # терминал 1
python run_client.py           # терминал 2
pytest                         # тесты
```
Тестовые учётки: `admin/admin123`, `tech/tech123` (смените перед реальным использованием). Остальные регистрируются в окне входа.
