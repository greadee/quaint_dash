"""Provider-neutral financial news ingestion and ranking."""

from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.repository import NewsRepository

__all__ = ["NewsIngestionService", "NewsRepository"]
