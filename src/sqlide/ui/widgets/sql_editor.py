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

from sqlide.db.completion import Candidate
from sqlide.sql.format import FormatError, format_sql, toggle_line_comments
from sqlide.sql.splitter import Span, span_lines, split, statement_at
from sqlide.ui.widgets.completion_popup import CompletionPopup

IMMEDIATE_RECALC_LIMIT = 20_000  # chars; above this, recompute spans with a short debounce
DEBOUNCE_S = 0.08
COMPLETE_DEBOUNCE_S = 0.05


class SqlEditor(TextArea):
    BINDINGS = [
        Binding("f5,ctrl+j,ctrl+enter", "run_statement", "Run", priority=True, id="editor.run"),
        Binding(
            "shift+f5,ctrl+shift+enter", "run_all", "Run all", priority=True, id="editor.run_all"
        ),
        Binding("ctrl+space,ctrl+@", "complete", "Complete", show=False, id="editor.complete"),
        Binding("ctrl+alt+l,f7", "format", "Format", show=False, id="editor.format"),
        Binding(
            "ctrl+slash,ctrl+underscore,alt+slash",
            "toggle_comment",
            "Comment",
            show=False,
            id="editor.toggle_comment",
        ),
    ]

    class RunRequested(Message):
        """User wants to execute these statements, in order."""

        def __init__(self, statements: list[str]) -> None:
            super().__init__()
            self.statements = statements

    class CompletionRequested(Message):
        """Cursor context changed (or the user asked): the owner supplies candidates."""

        def __init__(self, offset: int, text: str, manual: bool) -> None:
            super().__init__()
            self.offset, self.text, self.manual = offset, text, manual

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
        self._popup: CompletionPopup | None = None
        self._complete_timer: Timer | None = None
        self._prefix_len = 0
        self._accepting = False

    # --- configuration ---
    @property
    def dialect(self) -> str:
        return self._dialect

    @dialect.setter
    def dialect(self, value: str) -> None:
        self._dialect = value
        self._recalc()

    @property
    def blank_line(self) -> bool:
        return self._blank_line

    @blank_line.setter
    def blank_line(self, value: bool) -> None:
        self._blank_line = value
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
        self._maybe_complete()
        if len(self.text) <= IMMEDIATE_RECALC_LIMIT:
            self._recalc()
            return
        if self._timer:
            self._timer.stop()
        self._timer = self.set_timer(DEBOUNCE_S, self._recalc)

    def on_text_area_selection_changed(self, _: TextArea.SelectionChanged) -> None:
        self._update_frame()
        if self.completing:
            self._request_completion(manual=False)  # re-filter, or close when the cursor left

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

    # --- editing helpers ---
    def action_format(self) -> None:
        """Pretty-print the selection, or the framed statement."""
        sel = self.selection
        if not sel.is_empty:
            start, end = sorted((sel.start, sel.end))
            src = self.get_text_range(start, end)
        else:
            self._recalc()
            span = statement_at(self._spans, self.text, self._cursor_index())
            if span is None:
                self.app.notify("No statement at cursor", severity="warning")
                return
            doc = cast(Document, self.document)
            start, end = (
                doc.get_location_from_index(span.start),
                doc.get_location_from_index(span.end),
            )
            src = span.text(self.text)
        try:
            formatted = format_sql(src, self._dialect)
        except FormatError as e:
            self.app.notify(str(e), title="Cannot format", severity="warning")
            return
        if formatted != src:
            self.replace(formatted, start, end)

    def action_toggle_comment(self) -> None:
        sel = self.selection
        first, last = sorted((sel.start[0], sel.end[0]))
        if not sel.is_empty and sel.end[1] == 0 and sel.end[0] > sel.start[0]:
            last -= 1  # a selection ending at column 0 does not include that line
        lines = [self.document.get_line(i) for i in range(first, last + 1)]
        new = toggle_line_comments(lines)
        if new != lines:
            end_col = len(lines[-1])
            self.replace("\n".join(new), (first, 0), (last, end_col))

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

    # --- autocomplete (the data comes from the owner via CompletionRequested) ---
    @property
    def completing(self) -> bool:
        return self._popup is not None and self._popup.shown

    def action_complete(self) -> None:
        self._request_completion(manual=True)

    def _maybe_complete(self) -> None:
        """Auto-open after a dot; keep an open popup in sync while typing."""
        if self._accepting:
            return
        before = self.text[self._cursor_index() - 1 : self._cursor_index()]
        if before == "." or self.completing:
            self._request_completion(manual=False)

    def _request_completion(self, manual: bool) -> None:
        if self._complete_timer is not None:
            self._complete_timer.stop()
        self._complete_timer = self.set_timer(
            COMPLETE_DEBOUNCE_S,
            lambda: self.post_message(
                self.CompletionRequested(self._cursor_index(), self.text, manual)
            ),
        )

    def show_completions(self, items: list[Candidate], prefix_len: int) -> None:
        if not items or not self.has_focus:
            self.hide_completions()
            return
        if self._popup is None:
            self._popup = CompletionPopup()
            self.screen.mount(self._popup)
        self._prefix_len = prefix_len
        self._popup.show(items, self.cursor_screen_offset)

    def hide_completions(self) -> None:
        if self._popup is not None:
            self._popup.hide()

    def _accept_completion(self) -> None:
        popup = self._popup
        choice = popup.current if popup else None
        self.hide_completions()
        if choice is None:
            return
        end = self._cursor_index()
        doc = cast(Document, self.document)
        self._accepting = True
        try:
            self.replace(
                choice.text,
                doc.get_location_from_index(end - self._prefix_len),
                doc.get_location_from_index(end),
            )
        finally:
            self._accepting = False

    def on_blur(self) -> None:
        self.hide_completions()

    # Tab indents instead of moving focus (tab_behavior="indent"); Shift+Tab moves focus out.
    def on_key(self, event: Key) -> None:
        if self.completing and self._popup is not None:
            handled = {
                "down": lambda: self._popup.move(1),  # type: ignore[union-attr]
                "up": lambda: self._popup.move(-1),  # type: ignore[union-attr]
                "enter": self._accept_completion,
                "tab": self._accept_completion,
                "escape": self.hide_completions,
            }.get(event.key)
            if handled:
                event.stop()
                event.prevent_default()
                handled()
                return
        if event.key == "shift+tab":
            event.stop()
            self.screen.focus_previous()
