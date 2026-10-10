"""One console: editor + results + status, bound to one DB session and one SQL file."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.timer import Timer
from textual.widgets import TextArea

from sqlide.config.connections import Connection
from sqlide.consoles import CONSOLE, FILE, TabState
from sqlide.db.completion import candidates
from sqlide.db.metadata import MetaCache
from sqlide.db.result import DbError
from sqlide.db.session import DbSession
from sqlide.sql.context import analyze
from sqlide.sql.dialects import dialect_for
from sqlide.sql.snippets import is_ddl
from sqlide.sql.usage import extract
from sqlide.ui.widgets.console_export import ExportActions
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.result_panel import ResultPanel
from sqlide.ui.widgets.sql_editor import SqlEditor
from sqlide.ui.widgets.status_bar import StatusBar
from sqlide.workspace import Workspace

AUTOSAVE_S = 1.0


def one_line(sql: str, limit: int = 100) -> str:
    text = " ".join(sql.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ConsoleTab(ExportActions, Vertical):
    BINDINGS = [
        Binding("ctrl+b,ctrl+f2", "cancel", "Cancel", id="console.cancel"),
        Binding("f8", "toggle_tx", "Auto/Manual tx", id="console.toggle_tx"),
        Binding("f9", "commit", "Commit", id="console.commit"),
        Binding("f10", "rollback", "Rollback", id="console.rollback"),
    ]

    class TitleChanged(Message):
        def __init__(self, console: ConsoleTab) -> None:
            super().__init__()
            self.console = console

    class SchemaChanged(Message):
        """A DDL statement ran: cached metadata was dropped, views should reload."""

        def __init__(self, console: ConsoleTab) -> None:
            super().__init__()
            self.console = console

    class UsageChanged(Message):
        """A statement used tables: the schema tree's Recent list may have changed."""

        def __init__(self, console: ConsoleTab) -> None:
            super().__init__()
            self.console = console

    class ConnectRequested(Message):
        """The console has no session yet but knows which connection it wants."""

        def __init__(self, console: ConsoleTab, conn_name: str, then_run: list[str]) -> None:
            super().__init__()
            self.console, self.conn_name, self.then_run = console, conn_name, then_run

    def __init__(
        self, ws: Workspace, path: Path, kind: str = CONSOLE, conn_name: str = "", **kw
    ) -> None:
        super().__init__(**kw)
        self.ws = ws
        self.path = path
        self.kind = kind
        self.conn_name = conn_name
        self.conn: Connection | None = None
        self.session: DbSession | None = None
        self.meta: MetaCache | None = None
        self.meta_session: DbSession | None = None
        self._executing = False
        self._warned = ""
        self._usage_cache: dict[str, float] | None = None
        self._autosave: Timer | None = None
        try:
            self._initial, self._newline = ws.consoles.read(path)
        except FileNotFoundError:  # a new file named on the command line
            self._initial, self._newline = "", "\n"
        self._saved_text = self._initial

    def compose(self) -> ComposeResult:
        yield SqlEditor(self._initial, blank_line=self.ws.settings.split_on_blank_line, id="editor")
        yield ResultPanel(id="results")
        yield StatusBar(id="status")

    # --- parts ---
    @property
    def editor(self) -> SqlEditor:
        return self.query_one("#editor", SqlEditor)

    @property
    def panel(self) -> ResultPanel:
        return self.query_one("#results", ResultPanel)

    @property
    def status(self) -> StatusBar:
        return self.query_one("#status", StatusBar)

    @property
    def running(self) -> bool:
        return self._executing

    # --- identity / files ---
    @property
    def dirty(self) -> bool:
        if self.kind != FILE:
            return False
        editors = self.query("#editor")  # not mounted yet while the tab strip is being built
        return bool(editors) and cast(SqlEditor, editors.first()).text != self._saved_text

    @property
    def title(self) -> str:
        name = self.path.stem if self.kind == CONSOLE else self.path.name
        return (
            ("● " if self.dirty else "") + name + (f" [{self.conn_name}]" if self.conn_name else "")
        )

    def tab_state(self, active: bool) -> TabState:
        return TabState(self.kind, str(self.path), self.conn_name, active)

    def _title_changed(self) -> None:
        self.post_message(self.TitleChanged(self))

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        if self.kind == CONSOLE:
            if self._autosave is not None:
                self._autosave.stop()
            self._autosave = self.set_timer(AUTOSAVE_S, self.flush)
        else:
            self._title_changed()

    def flush(self) -> None:
        """Write a console's text to its autosave file now."""
        if self.kind == CONSOLE and self.is_mounted:
            self.ws.consoles.write(self.path, self.editor.text, self._newline)

    def save(self, path: Path | None = None) -> None:
        """Save to `path` (Save As) or the current file. A console becomes a file tab."""
        target = path or self.path
        self.ws.consoles.write(target, self.editor.text, self._newline)
        self.path, self.kind = target, FILE
        self._saved_text = self.editor.text
        self._title_changed()

    # --- connection ---
    async def attach(self, conn: Connection, session: DbSession) -> None:
        await self.detach()
        self.conn, self.session, self.conn_name = conn, session, conn.name
        self.meta = MetaCache(session)
        self.run_worker(self._open_meta_session(conn, self.meta), group="meta", exclusive=True)
        self.editor.dialect = dialect_for(conn.url, self.ws.driver(conn.driver).dialect)
        self._usage_cache = None
        self._backfill_usage(conn.name)
        self._refresh_tx(message="")
        self.status.update_state(connection=f"{conn.name} ({session.product})")
        self.panel.log_line(f"Connected: {conn.name}: {session.product}", "green")
        self._title_changed()

    async def _open_meta_session(self, conn: Connection, meta: MetaCache) -> None:
        second = await self.ws.connect_for_metadata(conn)
        if second is None:
            return
        if self.meta is not meta:  # detached or reconnected while we were connecting
            await second.close()
            return
        self.meta_session = second
        meta.use(second)

    async def detach(self) -> None:
        self.workers.cancel_group(self, "meta")
        if self.meta_session is not None:
            await self.meta_session.close()
            self.meta_session = None
        if self.session is not None:
            await self.session.close()
        self.conn = self.session = self.meta = None
        self.status.update_state(connection="not connected", tx="", message="")

    async def shutdown(self) -> None:
        """Called when the tab goes away: persist text, cancel work, close the connection."""
        self.cancel_export()
        self.flush()
        await self.detach()

    # --- transactions ---
    def _refresh_tx(self, message: str | None = None) -> None:
        s = self.session
        tx = (
            ""
            if s is None
            else "Auto"
            if s.autocommit
            else "Manual" + ("*" if s.pending_tx else "")
        )
        fields = {"tx": tx}
        if message is not None:
            fields["message"] = message
        self.status.update_state(**fields)

    async def action_toggle_tx(self) -> None:
        if self.session is None or self._executing:
            return
        try:
            await self.session.set_autocommit(not self.session.autocommit)
        except DbError as e:
            self.app.notify(str(e), severity="error")
        self._refresh_tx(
            message=f"transaction mode: {'Auto' if self.session.autocommit else 'Manual'}"
        )

    async def action_commit(self) -> None:
        await self._finish_tx(commit=True)

    async def action_rollback(self) -> None:
        await self._finish_tx(commit=False)

    async def _finish_tx(self, commit: bool) -> None:
        s = self.session
        if s is None or s.autocommit or self._executing:
            return
        try:
            await (s.commit() if commit else s.rollback())
        except DbError as e:
            self.app.notify(str(e), severity="error")
            return
        if self.meta is not None:  # DDL committed now becomes visible to the metadata session
            self.meta.refresh()
            self.post_message(self.SchemaChanged(self))
        self.panel.log_line("Committed" if commit else "Rolled back", "green")
        self._refresh_tx(message="committed" if commit else "rolled back")

    # --- autocomplete ---
    def on_sql_editor_completion_requested(self, message: SqlEditor.CompletionRequested) -> None:
        message.stop()
        self.run_worker(self._complete(message), group="complete", exclusive=True)

    async def _complete(self, req: SqlEditor.CompletionRequested) -> None:
        dialect = self.editor.dialect
        ctx = analyze(req.text, req.offset, dialect)
        if ctx is None or (not ctx.prefix and not ctx.qualifier and not req.manual):
            self.editor.hide_completions()
            return
        selected = self.conn.schemas if self.conn else None
        items = await candidates(
            ctx,
            self.meta,
            dialect,
            selected,
            self.conn.catalogs if self.conn else None,
            self.usage_scores(),
        )
        if self.meta is not None and self.meta.error and self.meta.error != self._warned:
            self._warned = self.meta.error  # say it once: otherwise "no tables" is a mystery
            self.status.update_state(message=f"autocomplete: {self.meta.error}")
            self.app.notify(self.meta.error, title="Autocomplete: no metadata", severity="warning")
        if len(items) == 1 and items[0].text.lower() == ctx.prefix.lower():
            items = []  # the word is already complete: nothing to offer, Enter stays a newline
        if self.editor._cursor_index() != req.offset:  # the user typed on; a newer request follows
            return
        self.editor.show_completions(items, ctx.replace_len)

    # --- execution ---
    def on_sql_editor_run_requested(self, message: SqlEditor.RunRequested) -> None:
        message.stop()
        self.run_statements(message.statements)

    def run_statements(self, statements: list[str]) -> None:
        if self.session is None:
            if self.conn_name and any(c.name == self.conn_name for c in self.ws.connections()):
                self.post_message(self.ConnectRequested(self, self.conn_name, statements))
            else:
                self.app.notify(
                    "Not connected: pick a connection in the sidebar", severity="warning"
                )
        elif self._executing:
            self.app.notify("A query is running (Ctrl+F2 cancels it)", severity="warning")
        else:
            self.run_worker(self._run(statements), group="run")

    def on_result_grid_summary(self, message: ResultGrid.Summary) -> None:
        message.stop()
        self.status.update_state(message=message.text)

    def action_cancel(self) -> None:
        if self.cancel_export():
            return
        if self.session is not None and self._executing:
            self.session.cancel()
            self.status.update_state(message="cancelling…")

    def _record(self, sql: str, ok: bool, elapsed_s: float, error: str = "") -> None:
        try:
            self.ws.history.add(self.conn_name, sql, ok, round(elapsed_s * 1000), error)
        except Exception as e:  # history must never break running queries
            self.app.log.warning(f"history: {e}")
        if ok:
            self._record_usage(sql)

    def _record_usage(self, sql: str) -> None:
        """Count the tables/columns of a successful statement (ranks autocomplete, Recent)."""
        try:
            uses = extract(sql, self.editor.dialect)
            if uses:
                self.ws.usage.record(self.conn_name, uses)
                self._usage_cache = None
                self.post_message(self.UsageChanged(self))
        except Exception as e:  # counters must never break running queries
            self.app.log.warning(f"usage: {e}")

    def _backfill_usage(self, name: str) -> None:
        """First connect after the upgrade: seed the counters from the saved history."""
        try:
            if not self.ws.usage.needs_backfill(name):
                return
            for entry in reversed(self.ws.history.search(connection=name, only_ok=True, limit=500)):
                self.ws.usage.record(name, extract(entry.sql, self.editor.dialect), ts=entry.ts)
            self.ws.usage.mark_backfilled(name)
        except Exception as e:
            self.app.log.warning(f"usage backfill: {e}")

    def usage_scores(self) -> dict[str, float]:
        if self._usage_cache is None:
            try:
                self._usage_cache = self.ws.usage.scores(self.conn_name) if self.conn_name else {}
            except Exception:
                self._usage_cache = {}
        return self._usage_cache

    async def _run(self, statements: list[str]) -> None:
        session = self.session
        assert session is not None
        self._executing = True
        self.status.update_state(message="running…")
        await self.panel.reset_results()
        n_results = 0
        last = ""
        try:
            for sql in statements:
                self.panel.log_line(f"▶ {one_line(sql)}", "bold")
                started = monotonic()
                try:
                    ex = await session.execute(sql, self.ws.settings.fetch_size)
                except DbError as e:
                    self._record(sql, False, monotonic() - started, str(e))
                    self.panel.log_error(f"✖ {e}" + (f"  [{e.sql_state}]" if e.sql_state else ""))
                    if str(e) == "Cancelled by user":
                        self.app.notify("Query cancelled", severity="warning")
                    else:
                        self.app.notify(str(e), title="Query failed", severity="error")
                    last = "failed"
                    break
                for w in ex.warnings:
                    self.panel.log_line(f"  {w}", "yellow")
                for item in ex.items:
                    if item.has_rows:
                        n_results += 1
                        grid = await self.panel.add_result(
                            f"Result {n_results}",
                            item.columns,
                            item.rows,
                            item.cursor,
                            self.ws.settings.fetch_size,
                            sql,
                        )
                        last = grid.summary_text
                    else:
                        last = f"{item.update_count} rows affected"
                        self.panel.log_line(f"  {last}")
                self._record(sql, True, ex.elapsed_s)
                if is_ddl(sql) and self.meta is not None:
                    self.meta.refresh()
                    self.post_message(self.SchemaChanged(self))
                self.panel.log_line(f"✔ {ex.elapsed_s * 1000:.0f} ms", "green")
                last = f"{last} in {ex.elapsed_s * 1000:.0f} ms"
        finally:
            self._executing = False
            self._refresh_tx(message=last)
            self.panel.show_first_result()
