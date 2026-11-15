"""Повторно используемые функции форматирования (не зависят от GUI)."""
from html import escape as esc

from .constants import CATEGORY, PRIORITY, STATUS


def label(mapping: dict, key: str) -> str:
    """Название по коду; если кода нет в справочнике, возвращает сам код."""
    return mapping.get(key, key)


def format_stats(stats: dict) -> str:
    """Текст статистики для показа пользователю."""
    def block(title, data, mapping):
        lines = "\n".join(f"  {label(mapping, k)}: {v}" for k, v in data.items()) or "  —"
        return f"{title}:\n{lines}"
    return "\n\n".join([block("По статусам", stats["by_status"], STATUS),
                        block("По категориям", stats["by_category"], CATEGORY),
                        block("По приоритетам", stats["by_priority"], PRIORITY)])


def format_ticket_html(t: dict) -> str:
    """HTML-карточка заявки; весь пользовательский текст экранируется (защита от HTML-инъекций)."""
    h = (f"<h3>#{t['id']} {esc(t['title'])}</h3><p><b>Статус:</b> {label(STATUS, t['status'])} | "
         f"<b>Приоритет:</b> {label(PRIORITY, t['priority'])} | "
         f"<b>Категория:</b> {label(CATEGORY, t['category'])}<br>"
         f"<b>Автор:</b> {esc(t['author'])} | <b>Исполнитель:</b> {esc(t['assignee'] or '—')} | "
         f"<b>Кабинет:</b> {esc(t['room'] or '—')}</p><p>{esc(t['description'])}</p>"
         f"<hr><b>Комментарии</b><br>")
    h += "".join(f"<p><i>{esc(c['username'])}, {c['created_at']}</i>: {esc(c['text'])}</p>"
                 for c in t.get("comments", []))
    h += "<hr><b>История</b><br>" + "".join(
        f"<small>{x['created_at']} — {esc(x['username'])}: {esc(x['action'])}</small><br>"
        for x in t.get("history", []))
    return h
