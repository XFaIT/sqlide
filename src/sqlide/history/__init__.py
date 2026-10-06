"""Query history (sqlite). Depends only on config paths."""

from sqlide.history.store import HistoryEntry, HistoryStore

__all__ = ["HistoryEntry", "HistoryStore"]
