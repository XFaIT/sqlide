"""One-line status: connection, transaction mode, last run summary."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar { height: 1; padding: 0 1; background: $panel; color: $text-muted; }
    """

    def __init__(self, **kw) -> None:
        super().__init__("", **kw)
        self.connection = "not connected"
        self.tx = ""
        self.message = ""
        self._refresh_text()

    def update_state(self, **fields: str) -> None:
        for k, v in fields.items():
            setattr(self, k, v)
        self._refresh_text()

    def _refresh_text(self) -> None:
        parts = [self.connection]
        if self.tx:
            parts.append(f"Tx: {self.tx}")
        if self.message:
            parts.append(self.message)
        self.update(Text(" · ".join(parts)))
