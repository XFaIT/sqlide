"""Schema tree: namespaces → tables/views → columns, loaded lazily from a MetaCache."""

from __future__ import annotations

import time

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
    needs_choice,
    table_matches,
    visible_namespaces,
)
from sqlide.db.result import DbError

ICON_NS, ICON_TABLE, ICON_VIEW, ICON_DB = "▣", "▤", "◫", "◆"


class CatalogRef:
    """Tree data of a catalog (database) node when names have three levels."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class RecentRef:
    """Tree data of the "Recent" node: the tables this connection used most lately."""

    __slots__ = ()


class SchemaTree(Tree[object]):
    BINDINGS = [
        Binding("f5", "refresh", "Refresh", id="schema.refresh"),
        Binding("i", "insert_name", "Insert name", id="schema.insert_name"),
        Binding("s", "choose_scope", "Schemas", id="schema.choose_scope"),
    ]

    class ScopeRequested(Message):
        """Pick which schemas/databases and tables the tree shows.

        `auto` is the first-connect prompt: the user never chose for this connection.
        """

        def __init__(self, auto: bool = False) -> None:
            super().__init__()
            self.auto = auto

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
        self._recent: list[Table] = []

    # --- binding to a connection ---
    def show(
        self,
        meta: MetaCache | None,
        label: str = "",
        conn: Connection | None = None,
        recent: list[Table] | None = None,
    ) -> None:
        """Show another connection's metadata (None: disconnected).

        `conn` carries the user's choice of schemas and table filter, `recent` the tables
        its queries used most lately.
        """
        self._meta, self._conn, self._label = meta, conn, label
        self._recent = recent or []
        self.root.set_label(self._root_label())
        self.root.remove_children()
        self.root.data = None
        if meta is not None:
            self.root.data = meta
            self.root.expand()
            self.run_worker(self._load_namespaces(meta, self.root), group="schema", exclusive=True)

    def set_recent(self, tables: list[Table]) -> None:
        """Replace the Recent node's tables (a query just used some)."""
        self._recent = tables
        if self._meta is None:
            return
        old = next((c for c in self.root.children if isinstance(c.data, RecentRef)), None)
        expanded = old is not None and old.is_expanded
        if old is not None:
            old.remove()
        self._add_recent(self.root, expand=expanded)

    def _add_recent(self, root: TreeNode, expand: bool = False) -> None:
        if not self._recent:
            return
        node = root.add(Text("★ Recent", style="bold"), data=RecentRef(), before=0)
        for t in self._recent:
            icon = ICON_VIEW if t.is_view else ICON_TABLE
            label = Text(f"{icon} {t.namespace + '.' if t.namespace else ''}{t.name}")
            node.add_leaf(label, data=t)
        if expand:
            node.expand()

    def action_refresh(self) -> None:
        """F5: the only thing that re-reads the database structure (nothing polls)."""
        if self._meta is not None:
            self._meta.refresh()
            self.show(self._meta, self._label, self._conn)

    def _root_label(self) -> str:
        label = self._label or "not connected"
        at = self._meta.cached_at if self._meta is not None else None
        if at:  # shown from the disk snapshot: it can be old, F5 reads the database again
            label += f"  ◷ cached {time.strftime('%d.%m %H:%M', time.localtime(at))}"
        return label

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

    async def _load_catalogs(self, meta: MetaCache, node: TreeNode, cats: list[str]) -> None:
        try:
            current = await meta.current_catalog()
        except DbError:
            current = ""
        if meta is not self._meta:
            return
        chosen = self._conn.catalogs if self._conn else None
        if chosen is None:
            chosen = [current] if current else []
        wanted = {c.lower() for c in chosen}
        shown = [c for c in cats if c.lower() in wanted]
        node.remove_children()
        opened = None
        for cat in shown:
            child = node.add(Text(f"{ICON_DB} {cat}"), data=CatalogRef(cat))
            if opened is None and cat.lower() == current.lower():
                opened = child
        if len(shown) < len(cats):
            hint = f"… {len(cats) - len(shown)} more databases hidden: press S to choose"
            node.add_leaf(Text(hint, style="dim italic"))
        if opened is not None:
            opened.expand()
        self._add_recent(node)
        conn = self._conn
        if conn is not None and conn.catalogs is None and conn.schemas is None:
            self.post_message(self.ScopeRequested(auto=True))

    async def _load_schemas(self, meta: MetaCache, node: TreeNode, ref: CatalogRef) -> None:
        self._placeholder(node)
        try:
            spaces = await meta.schemas_of(ref.name)
            at_home = ref.name.lower() == (await meta.current_catalog()).lower()
            current = (await meta.current_namespace()).lower() if at_home else ""
        except DbError as e:
            self._fail(node, e)
            return
        if meta is not self._meta:
            return
        selected = self._conn.schemas if self._conn else None
        spaces, hidden = visible_namespaces(spaces, current, selected)
        spaces = sorted(
            spaces, key=lambda n: (is_system_namespace(n.name), n.name.lower() != current)
        )
        node.remove_children()
        opened = None
        for ns in spaces:
            style = "dim" if is_system_namespace(ns.name) else ""
            child = node.add(Text(f"{ICON_NS} {ns.name}", style=style), data=ns)
            if opened is None and ns.name.lower() == current:
                opened = child
        if hidden:
            node.add_leaf(Text(f"… {hidden} more hidden: press S to choose", style="dim italic"))
        if not spaces and not hidden:
            node.add_leaf(Text("(no schemas)", style="dim italic"))
        if opened is not None:
            opened.expand()

    async def _load_namespaces(self, meta: MetaCache, node: TreeNode) -> None:
        self._placeholder(node)
        try:
            cats = await meta.catalogs()
            if cats:
                await self._load_catalogs(meta, node, cats)
                return
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
        selected = self._conn.schemas if self._conn else None
        all_spaces = spaces
        spaces, hidden = visible_namespaces(all_spaces, current, selected)
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
        self._add_recent(node)
        if self._conn is not None and self._conn.schemas is None and needs_choice(all_spaces):
            self.post_message(self.ScopeRequested(auto=True))  # first connect: ask, like DataGrip

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
        if isinstance(node.data, CatalogRef):
            self.run_worker(self._load_schemas(meta, node, node.data), group=f"cat-{node.id}")
        elif isinstance(node.data, Namespace):
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
