"""itdesk_core: библиотека ITDesk (API-клиент, справочники, форматирование, конфигурация)."""
__version__ = "0.2.0"

from .client import Api, ApiError  # noqa: E402
from .config import base_dir, db_path, load_config  # noqa: E402
from .constants import CATEGORY, PRIORITY, STATUS  # noqa: E402
from .formatting import format_stats, format_ticket_html, label  # noqa: E402

__all__ = ["Api", "ApiError", "CATEGORY", "PRIORITY", "STATUS", "base_dir", "db_path",
           "format_stats", "format_ticket_html", "label", "load_config"]
