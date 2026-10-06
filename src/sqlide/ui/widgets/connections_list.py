"""Sidebar list of saved connections (replaced by the schema tree in stage 9)."""

from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Label, ListItem, ListView

from sqlide.config.connections import Connection


class ConnectionItem(ListItem):
    def __init__(self, conn: Connection) -> None:
        super().__init__(Label(conn.name), Label(conn.url, classes="dim"))
        self.conn = conn


class ConnectionsList(ListView):
    BINDINGS = [
        Binding("e", "edit", "Edit"),
        Binding("delete", "delete", "Delete"),
    ]

    class EditRequested(Message):
        def __init__(self, conn: Connection) -> None:
            super().__init__()
            self.conn = conn

    class DeleteRequested(EditRequested):
        pass

    def reload(self, connections: list[Connection]) -> None:
        self.clear()
        for c in connections:
            self.append(ConnectionItem(c))
        if not connections:
            self.append(
                ListItem(Label("No connections yet"), Label("Ctrl+N to add one", classes="dim"))
            )
        if connections:  # Enter must work without pressing Down first
            self.call_after_refresh(setattr, self, "index", 0)

    @property
    def highlighted_conn(self) -> Connection | None:
        item = self.highlighted_child
        return item.conn if isinstance(item, ConnectionItem) else None

    def action_edit(self) -> None:
        if conn := self.highlighted_conn:
            self.post_message(self.EditRequested(conn))

    def action_delete(self) -> None:
        if conn := self.highlighted_conn:
            self.post_message(self.DeleteRequested(conn))
