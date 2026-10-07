"""Schema tree: namespaces → tables/views → columns, loaded lazily from a MetaCache."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from sqlide.config.connections import Connection
from sqlide.db.metadata import (
    Column,
    MetaCache,
    Namespace,
    Table,
    is_system_namespace,
    table_matches,
    visible_namespaces,
)
from sqlide.db.result import DbError

ICON_NS, ICON_TABLE, ICON_VIEW = "▣", "▤", "◫"


class SchemaTree(Tree[object]):
    BINDINGS = [
        Binding("f5", "refresh", "Refresh", id="schema.refresh"),
        Binding("i", "insert_name", "Insert name", id="schema.insert_name"),
        Binding("s", "choose_scope", "Schemas", id="schema.choose_scope"),
    ]

    class ScopeRequested(Message):
        """The user wants to pick which schemas/databases and tables the tree shows."""

    class TableChosen(Message):
        """`action` is "select" (open first rows) or "insert" (put the name into the editor)."""

        def __init__(self, table: Table, action: str) -> None:
            super().__init__()
            self.table, self.action = table, action

    def __init__(self, **kw) -> None:
        super().__init__("not connected", **kw)
        self.auto_expand = False  # Enter on a table runs it; Space / arrows expand
        self.show_root = True
        self._meta: MetaCache | None = None
        self._conn: Connection | None = None
        self._label = ""

    # --- binding to a connection ---
    def show(self, meta: MetaCache | None, label: str = "", conn: Connection | None = None) -> None:
        """Show another connection's metadata (None: disconnected).

        `conn` carries the user's choice of schemas and table filter.
        """
        self._meta, self._conn, self._label = meta, conn, label
        self.root.set_label(label or "not connected")
        self.root.remove_children()
        self.root.data = None
        if meta is not None:
            self.root.data = meta
            self.root.expand()
            self.run_worker(self._load_namespaces(meta, self.root), group="schema", exclusive=True)

    def action_refresh(self) -> None:
        """F5: the only thing that re-reads the database structure (nothing polls)."""
        if self._meta is not None:
            self._meta.refresh()
            self.show(self._meta, self._label, self._conn)

    def mark_stale(self) -> None:
        """A DDL statement ran: the cache is dropped, but the tree waits for F5."""
        if self._meta is not None:
            self.root.set_label(f"{self._label}  ⟳ changed, F5 to refresh")

    def action_choose_scope(self) -> None:
        if self._meta is not None and self._conn is not None:
            self.post_message(self.ScopeRequested())

    # --- lazy loading ---
    def _placeholder(self, node: TreeNode, text: str = "loading…") -> None:
        node.remove_children()
        node.add_leaf(Text(text, style="dim italic"))

    def _fail(self, node: TreeNode, e: Exception) -> None:
        node.remove_children()
        node.add_leaf(Text(f"✖ {str(e).splitlines()[0] if str(e) else e!r}", style="red"))

    async def _load_namespaces(self, meta: MetaCache, node: TreeNode) -> None:
        self._placeholder(node)
        try:
            spaces = await meta.namespaces()
        except DbError as e:
            self._fail(node, e)
            return
        if meta is not self._meta:
            return  # the user switched tabs meanwhile
        try:
            current = (await meta.current_namespace()).lower()
        except DbError:
            current = ""
        if meta is not self._meta:
            return  # switched or disconnected while we waited
        selected = self._conn.schemas if self._conn else []
        spaces, hidden = visible_namespaces(spaces, current, selected)
        # the working schema first, system schemas last and dimmed
        spaces = sorted(
            spaces, key=lambda n: (is_system_namespace(n.name), n.name.lower() != current)
        )
        node.remove_children()
        opened = None
        for ns in spaces:
            style = "dim" if is_system_namespace(ns.name) else ""
            child = node.add(Text(f"{ICON_NS} {ns.name or 'main'}", style=style), data=ns)
            if opened is None and ns.name.lower() == current:
                opened = child
        if opened is None and len(spaces) == 1:
            opened = node.children[0]
        if hidden:
            hint = f"… {hidden} more hidden: press S to choose"
            node.add_leaf(Text(hint, style="dim italic"))
        if opened is not None:
            opened.expand()

    async def _load_tables(self, meta: MetaCache, node: TreeNode, ns: Namespace) -> None:
        self._placeholder(node)
        try:
            tables = await meta.tables(ns)
        except DbError as e:
            self._fail(node, e)
            return
        node.remove_children()
        pattern = self._conn.table_filter if self._conn else ""
        shown = [t for t in tables if table_matches(t.name, pattern)]
        for t in shown:
            icon = ICON_VIEW if t.is_view else ICON_TABLE
            node.add(Text(f"{icon} {t.name}"), data=t)
        if not shown:
            node.add_leaf(
                Text("(empty)" if not tables else "(no match for filter)", style="dim italic")
            )
        elif len(shown) < len(tables):
            node.add_leaf(Text(f"… {len(tables) - len(shown)} filtered out", style="dim italic"))

    async def _load_columns(self, meta: MetaCache, node: TreeNode, table: Table) -> None:
        self._placeholder(node)
        try:
            cols = await meta.columns(table)
        except DbError as e:
            self._fail(node, e)
            return
        node.remove_children()
        for c in cols:
            node.add_leaf(_column_label(c), data=c)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[object]) -> None:
        node, meta = event.node, self._meta
        if meta is None or node.children:
            return  # already loaded
        if isinstance(node.data, Namespace):
            self.run_worker(self._load_tables(meta, node, node.data), group=f"ns-{node.id}")
        elif isinstance(node.data, Table):
            self.run_worker(self._load_columns(meta, node, node.data), group=f"t-{node.id}")

    # --- actions ---
    def on_tree_node_selected(self, event: Tree.NodeSelected[object]) -> None:
        event.stop()
        if isinstance(event.node.data, Table):
            self.post_message(self.TableChosen(event.node.data, "select"))
        elif event.node.allow_expand:
            event.node.toggle()

    def action_insert_name(self) -> None:
        node = self.cursor_node
        if node is not None and isinstance(node.data, Table):
            self.post_message(self.TableChosen(node.data, "insert"))


def _column_label(c: Column) -> Text:
    text = Text()
    text.append("🔑 " if c.primary_key else "   ")
    text.append(c.name)
    text.append(f"  {c.type_name}{'' if c.nullable else ' not null'}", style="dim")
    return text
