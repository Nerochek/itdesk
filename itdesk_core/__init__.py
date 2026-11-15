"""itdesk_core: библиотека ITDesk (API-клиент, справочники, форматирование)."""
from .client import Api, ApiError
from .constants import CATEGORY, PRIORITY, STATUS
from .formatting import format_stats, format_ticket_html, label

__all__ = ["Api", "ApiError", "CATEGORY", "PRIORITY", "STATUS",
           "format_stats", "format_ticket_html", "label"]
__version__ = "0.1.0"
