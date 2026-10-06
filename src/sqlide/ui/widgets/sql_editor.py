"""SQL editor: TextArea + a frame around the statement that would run now."""

from __future__ import annotations

from typing import cast

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.color import Color
from textual.document._document import Document
from textual.events import Key
from textual.geometry import Offset
from textual.message import Message
from textual.strip import Strip
from textual.timer import Timer
from textual.widgets import TextArea

from sqlide.sql.splitter import Span, span_lines, split, statement_at

IMMEDIATE_RECALC_LIMIT = 20_000  # chars; above this, recompute spans with a short debounce
DEBOUNCE_S = 0.08


class SqlEditor(TextArea):
    BINDINGS = [
        Binding("f5,ctrl+j,ctrl+enter", "run_statement", "Run", priority=True),
        Binding("shift+f5,ctrl+shift+enter", "run_all", "Run all", priority=True),
    ]

    class RunRequested(Message):
        """User wants to execute these statements, in order."""

        def __init__(self, statements: list[str]) -> None:
            super().__init__()
            self.statements = statements

    def __init__(self, text: str = "", *, dialect: str = "generic", blank_line: bool = True,
                 **kw) -> None:  # fmt: skip
        super().__init__(
            text,
            language="sql",
            theme="monokai",
            show_line_numbers=True,
            soft_wrap=False,
            tab_behavior="indent",
            placeholder="-- connect (sidebar: Enter), then F5 / Ctrl+J runs the framed statement",
            **kw,
        )
        self._dialect = dialect
        self._blank_line = blank_line
        self._spans: list[Span] = []
        self._frame: tuple[int, int] | None = None
        self._timer: Timer | None = None

    # --- configuration ---
    @property
    def dialect(self) -> str:
        return self._dialect

    @dialect.setter
    def dialect(self, value: str) -> None:
        self._dialect = value
        self._recalc()

    # --- spans and frame ---
    def _recalc(self) -> None:
        self._spans = split(self.text, self._dialect, self._blank_line)
        self._update_frame()

    def _cursor_index(self) -> int:
        """Cursor as a character offset into `self.text`."""
        return cast(Document, self.document).get_index_from_location(self.cursor_location)

    def _update_frame(self) -> None:
        frame = None
        if self.selection.is_empty:
            span = statement_at(self._spans, self.text, self._cursor_index())
            if span:
                frame = span_lines(self.text, span)
        if frame != self._frame:
            self._frame = frame
            self.refresh()

    @property
    def frame_lines(self) -> tuple[int, int] | None:
        """(first, last) 0-based lines of the framed statement, or None."""
        return self._frame

    def on_mount(self) -> None:
        self._recalc()

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        if len(self.text) <= IMMEDIATE_RECALC_LIMIT:
            self._recalc()
            return
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(DEBOUNCE_S, self._recalc)

    def on_text_area_selection_changed(self, _: TextArea.SelectionChanged) -> None:
        self._update_frame()

    # --- run actions ---
    def statements_to_run(self) -> list[str]:
        """Selection (split into statements) wins; otherwise the framed statement."""
        sel = self.selected_text
        if sel.strip():
            parts = [s.text(sel) for s in split(sel, self._dialect, self._blank_line)]
            return parts or [sel.strip()]
        self._recalc()  # never run from stale spans
        span = statement_at(self._spans, self.text, self._cursor_index())
        return [span.text(self.text)] if span else []

    def action_run_statement(self) -> None:
        stmts = self.statements_to_run()
        if stmts:
            self.post_message(self.RunRequested(stmts))
        else:
            self.app.notify("No statement at cursor", severity="warning")

    def action_run_all(self) -> None:
        self._recalc()
        stmts = [s.text(self.text) for s in self._spans]
        if stmts:
            self.post_message(self.RunRequested(stmts))
        else:
            self.app.notify("Nothing to run", severity="warning")

    # --- drawing ---
    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        if self._frame is None or not self.show_line_numbers:
            return strip
        line, _ = self.wrapped_document.offset_to_location(Offset(0, y + self.scroll_offset.y))
        first, last = self._frame
        if not first <= line <= last:
            return strip
        mark = "▏" if first == last else "┏" if line == first else "┗" if line == last else "┃"
        accent, tint = self._frame_colors()
        segs = list(strip)
        head = segs[0]
        segs[0] = Segment(mark + head.text[1:], (head.style or Style()) + Style(color=accent))
        segs = [Segment(s.text, (s.style or Style()) + tint, s.control) for s in segs]
        return Strip(segs, strip.cell_length)

    def _frame_colors(self) -> tuple[str, Style]:
        theme = self.app.current_theme
        accent = Color.parse(theme.primary)
        base = Color.parse(theme.background if theme.background else "#1e1e1e")
        return accent.hex, Style(bgcolor=base.blend(accent, 0.14).hex)

    # Tab indents instead of moving focus (tab_behavior="indent"); Shift+Tab moves focus out.
    def on_key(self, event: Key) -> None:
        if event.key == "shift+tab":
            event.stop()
            self.screen.focus_previous()
