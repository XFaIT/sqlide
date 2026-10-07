"""Pick which schemas/databases and tables the schema tree shows (like DataGrip's selector).

Two shapes: a flat list of schemas, or, when the connection has several databases (catalogs),
a list of databases on the left and the schemas of the highlighted database on the right.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList
from textual.widgets.selection_list import Selection

from sqlide.db.metadata import Namespace, is_system_namespace

SchemaLoader = Callable[[str], Awaitable[list[Namespace]]]


class ScopeChoice:
    """What the user ticked. An empty list means "show none". `catalogs` is None when flat."""

    __slots__ = ("catalogs", "schemas", "table_filter")

    def __init__(
        self, schemas: list[str], table_filter: str, catalogs: list[str] | None = None
    ) -> None:
        self.schemas, self.table_filter, self.catalogs = schemas, table_filter, catalogs


class ScopeScreen(ModalScreen[ScopeChoice | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "OK", priority=True),
    ]

    def __init__(
        self,
        spaces: list[Namespace],
        chosen: list[str],
        table_filter: str,
        *,
        catalogs: list[str] | None = None,
        chosen_catalogs: list[str] | None = None,
        loader: SchemaLoader | None = None,
        start_catalog: str = "",
    ) -> None:
        super().__init__()
        self._catalogs = catalogs
        self._loader = loader
        self._start = start_catalog
        self._table_filter = table_filter
        self._keys: dict[str, str] = {}  # lower-case key -> key as the database spells it
        self._known: list[Namespace] = []
        self._by_catalog: dict[str, list[Namespace]] = {}
        self._cat_names = {c.lower(): c for c in catalogs or []}
        self._chosen_cats = {c.lower() for c in chosen_catalogs or []}
        self._current_cat = ""
        for ns in spaces:
            self._remember(ns)
        self._chosen = {k.lower() for k in chosen}
        for k in chosen:
            self._keys.setdefault(k.lower(), k)

    def _remember(self, ns: Namespace) -> None:
        self._keys.setdefault(ns.key.lower(), ns.key)
        self._known.append(ns)

    # --- layout ---
    def compose(self) -> ComposeResult:
        title = "Databases and schemas" if self._catalogs else "Schemas and databases"
        with Vertical(id="scope-box"):
            yield Label(title, id="scope-title")
            yield Input(placeholder="type to find a schema", id="scope-find")
            with Horizontal(id="scope-panes"):
                if self._catalogs:
                    yield SelectionList[str](id="scope-cats")
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
        if self._catalogs:
            cats = self.query_one("#scope-cats", SelectionList)
            cats.add_options(
                Selection(c, c, c.lower() in self._chosen_cats) for c in self._catalogs
            )
            start = self._cat_names.get(self._start.lower()) or self._catalogs[0]
            cats.highlighted = self._catalogs.index(start)
            self.run_worker(self._open_catalog(start), group="cat", exclusive=True)
        else:
            self._fill()
        self.query_one("#scope-find", Input).focus()

    async def _open_catalog(self, catalog: str) -> None:
        assert self._loader is not None
        if catalog not in self._by_catalog:
            self._sync()
            try:
                spaces = await self._loader(catalog)
            except Exception as e:  # noqa: BLE001 - shown in the dialog, never fatal
                self.query_one("#scope-count", Label).update(f"cannot list {catalog}: {e}")
                return
            self._by_catalog[catalog] = spaces
            for ns in spaces:
                self._remember(ns)
        self._sync()
        self._current_cat = catalog
        self._fill()

    # --- list handling ---
    def _listed(self) -> list[Namespace]:
        if self._catalogs:
            return self._by_catalog.get(self._current_cat, [])
        return self._known

    def _shown(self) -> list[Namespace]:
        needle = self.query_one("#scope-find", Input).value.strip().lower()
        return [n for n in self._listed() if needle in n.name.lower()]

    def _sync(self) -> None:
        """Fold what is ticked in the lists now into the choice, whatever events are pending."""
        lst = self.query_one("#scope-list", SelectionList)
        listed = {str(cast(Selection[str], o).value).lower() for o in lst.options}
        picked = {str(v).lower() for v in lst.selected}
        self._chosen = (self._chosen - listed) | picked
        if self._catalogs:
            cats = self.query_one("#scope-cats", SelectionList)
            all_cats = {str(cast(Selection[str], o).value).lower() for o in cats.options}
            self._chosen_cats = (self._chosen_cats - all_cats) | {
                str(v).lower() for v in cats.selected
            }

    def _fill(self) -> None:
        self._sync()
        lst = self.query_one("#scope-list", SelectionList)
        lst.clear_options()
        lst.add_options(
            Selection(
                (n.name or "main") + ("  (system)" if is_system_namespace(n.name) else ""),
                n.key,
                n.key.lower() in self._chosen,
            )
            for n in self._shown()
        )
        self._count()

    def _count(self) -> None:
        text = f"{len(self._chosen)} schemas selected"
        if self._catalogs:
            text += f", {len(self._chosen_cats)} databases"
        self.query_one("#scope-count", Label).update(f"{text}. Ctrl+S or OK to apply.")

    # --- events ---
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "scope-find":
            self._fill()

    def on_selection_list_selected_changed(self, _: SelectionList.SelectedChanged) -> None:
        self._sync()
        self._count()

    def on_selection_list_selection_highlighted(
        self, event: SelectionList.SelectionHighlighted
    ) -> None:
        if event.selection_list.id == "scope-cats" and self._loader is not None:
            catalog = str(event.selection.value)
            if catalog != self._current_cat:
                self.run_worker(self._open_catalog(catalog), group="cat", exclusive=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "scope-ok":
                self.action_save()
            case "scope-cancel":
                self.dismiss(None)
            case "scope-all":
                self._sync()
                self._chosen |= {n.key.lower() for n in self._shown()}
                self._fill()
            case "scope-none":
                self._chosen.clear()
                self._chosen_cats.clear()
                self.query_one("#scope-list", SelectionList).deselect_all()
                if self._catalogs:
                    self.query_one("#scope-cats", SelectionList).deselect_all()
                self._count()

    def action_save(self) -> None:
        self._sync()
        keys = [self._keys[k] for k in self._keys if k in self._chosen]
        catalogs = None
        if self._catalogs:
            catalogs = [c for c in self._catalogs if c.lower() in self._chosen_cats]
        table_filter = self.query_one("#scope-tables", Input).value.strip()
        self.dismiss(ScopeChoice(keys, table_filter, catalogs))

    def action_cancel(self) -> None:
        self.dismiss(None)
