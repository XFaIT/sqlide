"""The tab strip of consoles: create, restore, close, persist."""

from __future__ import annotations

from pathlib import Path

from textual.markup import escape
from textual.widgets import TabbedContent, TabPane

from sqlide.consoles import CONSOLE, FILE, TabState
from sqlide.ui.widgets.console_tab import ConsoleTab
from sqlide.workspace import Workspace


class ConsoleTabs(TabbedContent):
    def __init__(self, ws: Workspace, panes: list[TabPane], initial: str, seq: int, **kw) -> None:
        super().__init__(initial=initial, **kw)
        for pane in panes:
            self.compose_add_child(pane)  # same hook the `with TabbedContent():` form uses
        self.ws = ws
        self._seq = seq

    @classmethod
    def build(cls, ws: Workspace, states: list[TabState], files: list[Path], **kw) -> ConsoleTabs:
        """Tabs of the previous run plus files named on the command line (synchronous)."""
        consoles: list[tuple[ConsoleTab, bool]] = []
        for st in states:
            path = Path(st.path)
            if path.exists():
                consoles.append((ConsoleTab(ws, path, st.kind, st.connection), st.active))
        open_paths = {c.path.resolve() for c, _ in consoles}
        opened_from_cli: ConsoleTab | None = None
        for f in files:
            known = next((c for c, _ in consoles if c.path.resolve() == f.resolve()), None)
            if known is None and f.resolve() not in open_paths:
                known = ConsoleTab(ws, f, FILE)
                consoles.append((known, False))
            opened_from_cli = known
        if not consoles:
            consoles.append((ConsoleTab(ws, ws.consoles.new_console_file(None), CONSOLE), True))
        active = opened_from_cli or next((c for c, a in consoles if a), consoles[0][0])
        panes, initial = [], ""
        for i, (console, _) in enumerate(consoles, 1):
            pane = TabPane(escape(console.title), console, id=f"c{i}")
            panes.append(pane)
            if console is active:
                initial = f"c{i}"
        return cls(ws, panes, initial, len(consoles), **kw)

    # --- lookup ---
    def consoles(self) -> list[ConsoleTab]:
        return list(self.query(ConsoleTab))

    @property
    def active_console(self) -> ConsoleTab | None:
        pane = self.active_pane
        return pane.query_one(ConsoleTab) if pane is not None else None

    def find_file(self, path: Path) -> ConsoleTab | None:
        want = path.resolve()
        return next((c for c in self.consoles() if c.path.resolve() == want), None)

    # --- create / close ---
    async def add_console(
        self,
        *,
        kind: str = CONSOLE,
        path: Path | None = None,
        conn_name: str = "",
        activate: bool = True,
    ) -> ConsoleTab:
        if path is None:
            path = self.ws.consoles.new_console_file(conn_name or None)
        self._seq += 1
        pane_id = f"c{self._seq}"
        console = ConsoleTab(self.ws, path, kind, conn_name)
        await self.add_pane(TabPane(escape(console.title), console, id=pane_id))
        if activate:
            self.active = pane_id
        self.persist()
        return console

    async def close_console(self, console: ConsoleTab) -> None:
        pane = console.parent
        await console.shutdown()
        console.forget_results()
        if isinstance(pane, TabPane) and pane.id:
            await self.remove_pane(pane.id)
        if not self.consoles():
            await self.add_console()
        self.persist()

    async def shutdown(self) -> None:
        """App is quitting: remember the tabs, then stop every console."""
        self.persist()
        for console in self.consoles():
            await console.shutdown()

    # --- titles ---
    def on_console_tab_title_changed(self, message: ConsoleTab.TitleChanged) -> None:
        message.stop()
        pane = message.console.parent
        if isinstance(pane, TabPane) and pane.id:
            self.get_tab(pane.id).label = escape(message.console.title)  # type: ignore[assignment]
        self.persist()

    def on_tabbed_content_tab_activated(self, _: TabbedContent.TabActivated) -> None:
        self.persist()

    # --- persistence ---
    def persist(self) -> None:
        active = self.active_console
        states = [c.tab_state(c is active) for c in self.consoles()]
        if states:
            self.ws.consoles.save_state(states)


__all__ = ["CONSOLE", "FILE", "ConsoleTabs"]
