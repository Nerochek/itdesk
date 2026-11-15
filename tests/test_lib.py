"""Тесты библиотеки itdesk_core (п.13)."""
from typing import get_args

import pytest

from itdesk_core import CATEGORY, PRIORITY, STATUS, Api, ApiError, format_stats, format_ticket_html, label
from server import main


def test_constants_match_server_schema():
    assert set(STATUS) == set(get_args(main.Status))
    assert set(PRIORITY) == set(get_args(main.Priority))
    assert set(CATEGORY) == set(get_args(main.Category))


def test_label_fallback():
    assert label(STATUS, "new") == "Новая"
    assert label(STATUS, "unknown") == "unknown"


def test_ticket_html_escapes_user_text():
    t = {"id": 1, "title": "<script>x</script>", "status": "new", "priority": "low",
         "category": "other", "author": "a", "assignee": None, "room": "", "description": "<b>d</b>",
         "comments": [{"username": "u", "created_at": "t", "text": "<i>c</i>"}], "history": []}
    out = format_ticket_html(t)
    assert "<script>" not in out and "&lt;script&gt;" in out and "&lt;i&gt;" in out


def test_format_stats():
    text = format_stats({"by_status": {"new": 2}, "by_category": {}, "by_priority": {"high": 1}})
    assert "Новая: 2" in text and "Высокий: 1" in text and "—" in text


def test_api_reports_unreachable_server():
    with pytest.raises(ApiError):
        Api("http://127.0.0.1:1").login("user", "password")
