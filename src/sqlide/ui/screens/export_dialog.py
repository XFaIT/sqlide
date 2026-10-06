"""Export dialog: format, scope, path, per-format options. Returns an ExportRequest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Select, Static, Switch

from sqlide import export


@dataclass(frozen=True, slots=True)
class ExportContext:
    n_view: int
    selection: tuple[int, int] | None  # (rows, cols) when more than one cell is selected
    can_requery: bool
    more_rows: bool  # the loaded rows are only part of the result


@dataclass(frozen=True, slots=True)
class ExportRequest:
    format: str
    scope: str  # "view" | "selection" | "all"
    path: Path
    header: bool
    delimiter: str
    bom: bool
    table_name: str


def default_path(ext: str) -> str:
    return str(Path.cwd() / f"result_{datetime.now():%Y%m%d_%H%M%S}{ext}")


class ExportScreen(ModalScreen[ExportRequest | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, ctx: ExportContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._prev_ext = export.get("csv").extension

    def compose(self) -> ComposeResult:
        c = self._ctx
        default_scope = "all" if c.more_rows and c.can_requery else "view"
        with Vertical(classes="dialog wide"):
            yield Label("Export result", classes="title")
            yield Label("Format")
            yield Select(
                [(e.label, e.name) for e in export.all_exporters()],
                value="csv",
                allow_blank=False,
                id="format",
            )
            yield Label("Data")
            with RadioSet(id="scope"):
                view_label = f"Loaded rows, as shown ({c.n_view})" + (
                    "  - more rows exist" if c.more_rows else ""
                )
                yield RadioButton(view_label, id="view", value=default_scope == "view")
                if c.selection:
                    yield RadioButton(
                        f"Selection ({c.selection[0]} x {c.selection[1]})", id="selection"
                    )
                if c.can_requery:
                    yield RadioButton(
                        "Whole result (re-run the query)", id="all", value=default_scope == "all"
                    )
            yield Label("File")
            yield Input(default_path(self._prev_ext), id="path")
            with Horizontal(classes="row", id="opt-header"):
                yield Label("Header row")
                yield Switch(True, id="header")
            with Horizontal(classes="row", id="opt-csv"):
                yield Label("Delimiter")
                yield Input(",", id="delimiter", max_length=1)
                yield Label("  UTF-8 BOM (for Excel)")
                yield Switch(False, id="bom")
            with Horizontal(classes="row", id="opt-sql"):
                yield Label("Table name")
                yield Input("table_name", id="table_name")
            with Horizontal(classes="row"):
                yield Label("Overwrite existing file")
                yield Switch(False, id="overwrite")
            yield Static("", id="error", classes="error")
            with Horizontal(classes="buttons"):
                yield Button("Export", variant="primary", id="export")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._sync_options("csv")
        self.query_one("#path", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "format" and isinstance(event.value, str):
            self._swap_extension(event.value)
            self._sync_options(event.value)

    def _swap_extension(self, fmt: str) -> None:
        path = self.query_one("#path", Input)
        new_ext = export.get(fmt).extension
        if path.value.endswith(self._prev_ext):
            path.value = path.value[: -len(self._prev_ext)] + new_ext
        self._prev_ext = new_ext

    def _sync_options(self, fmt: str) -> None:
        shows = {
            "opt-header": fmt in ("csv", "tsv", "xlsx", "html", "markdown"),
            "opt-csv": fmt == "csv",
            "opt-sql": fmt == "sql",
        }
        for id_, visible in shows.items():
            self.query_one(f"#{id_}").display = visible

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
            self._submit()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        error = self.query_one("#error", Static)
        raw = self.query_one("#path", Input).value.strip()
        if not raw:
            error.update("Path is empty")
            return
        path = Path(raw).expanduser()
        if path.is_dir():
            error.update(f"{path} is a directory")
            return
        if path.exists() and not self.query_one("#overwrite", Switch).value:
            error.update("File exists: switch on 'Overwrite existing file'")
            return
        scope_set = self.query_one("#scope", RadioSet)
        scope = scope_set.pressed_button.id if scope_set.pressed_button else "view"
        self.dismiss(
            ExportRequest(
                format=str(self.query_one("#format", Select).value),
                scope=scope or "view",
                path=path,
                header=self.query_one("#header", Switch).value,
                delimiter=self.query_one("#delimiter", Input).value or ",",
                bom=self.query_one("#bom", Switch).value,
                table_name=self.query_one("#table_name", Input).value.strip() or "table_name",
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
