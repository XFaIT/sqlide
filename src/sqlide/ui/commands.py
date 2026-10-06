"""Entries of the command palette (Ctrl+P): every user action by name."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from textual.app import SystemCommand

if TYPE_CHECKING:
    from sqlide.app import SqlideApp


def commands(app: SqlideApp) -> Iterator[SystemCommand]:
    main = app.main

    def on_console(method: str) -> Callable[[], None]:
        def run() -> None:
            getattr(main.console, method)()

        return run

    def on_editor(method: str) -> Callable[[], None]:
        def run() -> None:
            getattr(main.console.editor, method)()

        return run

    def screen(action: str) -> Callable[[], None]:
        def run() -> None:
            getattr(main, action)()

        return run

    table: list[tuple[str, str, Callable[[], None]]] = [
        (
            "Run statement",
            "Execute the framed statement or selection",
            on_editor("action_run_statement"),
        ),
        ("Run all", "Execute every statement in the editor", on_editor("action_run_all")),
        ("Cancel query", "Cancel the running query or export", on_console("action_cancel")),
        ("Commit", "Commit the manual transaction", on_console("action_commit")),
        ("Rollback", "Roll back the manual transaction", on_console("action_rollback")),
        ("Toggle auto/manual transaction", "Switch commit mode", on_console("action_toggle_tx")),
        ("Format SQL", "Pretty-print selection or statement", on_editor("action_format")),
        ("Toggle comment", "Comment/uncomment lines", on_editor("action_toggle_comment")),
        ("New connection", "Add a database connection", screen("action_new_connection")),
        ("New console", "Open a new SQL console tab", screen("action_new_console")),
        ("Close tab", "Close the current tab", screen("action_close_console")),
        ("Open SQL file", "Open a .sql file in a tab", screen("action_open_file")),
        ("Save", "Save the console or file", screen("action_save_file")),
        ("Query history", "Search executed statements", screen("action_history")),
        ("Refresh schema", "Reload the schema tree", lambda: main.schema.action_refresh()),
        ("Drivers", "Download or add JDBC drivers", screen("action_drivers")),
        ("Settings", "Theme, paging, history size", screen("action_settings")),
    ]
    for title, help_text, callback in table:
        yield SystemCommand(title, help_text, callback)
