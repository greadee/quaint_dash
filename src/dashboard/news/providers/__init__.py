"""Financial news provider adapters."""

from dashboard.news.providers.base import NewsProvider
from dashboard.news.providers.mock_provider import MockNewsProvider

__all__ = ["MockNewsProvider", "NewsProvider"]
