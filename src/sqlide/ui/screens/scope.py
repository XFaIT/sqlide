"""Pick which schemas/databases and tables the schema tree shows (like DataGrip's selector)."""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList
from textual.widgets.selection_list import Selection

from sqlide.db.metadata import Namespace, is_system_namespace


class ScopeChoice:
    """`schemas` empty means automatic (small database: all, big one: the working schema)."""

    __slots__ = ("schemas", "table_filter")

    def __init__(self, schemas: list[str], table_filter: str) -> None:
        self.schemas, self.table_filter = schemas, table_filter


class ScopeScreen(ModalScreen[ScopeChoice | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "OK", priority=True),
    ]

    def __init__(self, spaces: list[Namespace], chosen: list[str], table_filter: str) -> None:
        super().__init__()
        self._spaces = spaces
        self._chosen = {n.lower() for n in chosen}
        self._table_filter = table_filter

    def compose(self) -> ComposeResult:
        with Vertical(id="scope-box"):
            yield Label(f"Schemas and databases ({len(self._spaces)})", id="scope-title")
            yield Input(placeholder="type to find a schema", id="scope-find")
            yield SelectionList[str](id="scope-list")
            yield Label("Tables to show (names or globs, comma separated; empty = all)")
            yield Input(self._table_filter, placeholder="e.g. fact_*, dim_*", id="scope-tables")
            yield Label(id="scope-count", classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("OK", id="scope-ok", variant="primary")
                yield Button("Select shown", id="scope-all")
                yield Button("Clear all", id="scope-none")
                yield Button("Cancel", id="scope-cancel")

    def on_mount(self) -> None:
        self._fill()
        self.query_one("#scope-find", Input).focus()

    def _shown(self) -> list[Namespace]:
        needle = self.query_one("#scope-find", Input).value.strip().lower()
        return [n for n in self._spaces if needle in n.name.lower()]

    def _sync(self) -> None:
        """Fold what is ticked in the list now into the choice, whatever events are pending."""
        lst = self.query_one("#scope-list", SelectionList)
        listed = {str(cast(Selection[str], o).value).lower() for o in lst.options}
        picked = {str(v).lower() for v in lst.selected}
        self._chosen = (self._chosen - listed) | picked

    def _fill(self) -> None:
        self._sync()
        lst = self.query_one("#scope-list", SelectionList)
        lst.clear_options()
        lst.add_options(
            Selection(
                (n.name or "main") + ("  (system)" if is_system_namespace(n.name) else ""),
                n.name,
                n.name.lower() in self._chosen,
            )
            for n in self._shown()
        )
        self._count()

    def _count(self) -> None:
        hint = f"{len(self._chosen)} selected. Nothing selected = automatic."
        self.query_one("#scope-count", Label).update(hint)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "scope-find":
            self._fill()

    def on_selection_list_selected_changed(self, _: SelectionList.SelectedChanged) -> None:
        self._sync()
        self._count()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "scope-ok":
                self.action_save()
            case "scope-cancel":
                self.dismiss(None)
            case "scope-all":
                self._sync()
                self._chosen |= {n.name.lower() for n in self._shown()}
                self._fill()
            case "scope-none":
                self._chosen.clear()
                self._fill_unsynced()

    def _fill_unsynced(self) -> None:
        """Redraw from the choice as it is (after Clear all the old ticks must not come back)."""
        lst = self.query_one("#scope-list", SelectionList)
        lst.deselect_all()
        self._count()

    def action_save(self) -> None:
        self._sync()
        names = [n.name for n in self._spaces if n.name.lower() in self._chosen]
        table_filter = self.query_one("#scope-tables", Input).value.strip()
        self.dismiss(ScopeChoice(names, table_filter))

    def action_cancel(self) -> None:
        self.dismiss(None)
