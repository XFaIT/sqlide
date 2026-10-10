# sqlide

A DataGrip-style SQL IDE that runs in your terminal. Connect to any database over JDBC,
write SQL in an editor that outlines the statement about to run, and browse results in
sortable, copyable tables that export to CSV, XLSX and more.

Works on Linux, macOS and WSL.

## Features

- **Any JDBC database.** PostgreSQL and ClickHouse work out of the box; MySQL, MariaDB,
  Oracle, SQL Server, H2, SQLite and DuckDB are one keypress away. Add your own driver from
  jar files or Maven coordinates, as in DataGrip. Drivers are downloaded from Maven Central
  (checksum verified) and each one gets its own class loader.
- **Framed statement.** The statement under the cursor is outlined in the gutter; `F5`
  runs it, a selection runs the selection, `Shift+F5` runs the whole file. Dialect-aware
  splitting: `$$` quotes, nested comments, Oracle `/`, SQL Server `GO`, procedural blocks.
- **Result grid.** Sort by several columns, filter, select a rectangle, view long values,
  load more rows on demand. Copy as TSV, CSV, Markdown, JSON or `INSERT` statements.
- **Export.** CSV, TSV, JSON, JSON Lines, Markdown, SQL inserts, HTML, XLSX. Export the loaded
  rows or re-run the query and stream the full result to disk, with progress and cancel.
- **Schema tree and autocomplete.** Lazy metadata, `SELECT *` on Enter, alias-aware column
  completion, keywords and functions per dialect. Like DataGrip, you choose what to show: on the
  first connect to a database with several schemas a picker opens (schemas or databases, plus a
  table name filter such as `fact_*`); until you choose, only the working schema is loaded.
  `S` in the tree reopens the picker; the choice is saved per connection. On SQL Server,
  Databricks and Snowflake the picker has two panes (databases left, their schemas right), so
  databases you did not connect to by default can be added; autocomplete knows
  `database.schema.table` names.
- **Consoles and files.** Tabs with their own connection; consoles autosave and come back
  after a restart; open and save `.sql` files (`sqlide a.sql b.sql`).
- **Toolbar.** One row of icons instead of a footer; hover for the name, the key and what
  it does. `ascii_icons = true` in `settings.toml` shows words instead of symbols.
- **Results that stay.** A new run only replaces unpinned result tabs; pin one (`p`, or the
  pin button above the tabs) to keep it next to the next results. Pinned tabs and the latest
  results are saved and come back after a restart. Buttons: pin, copy, export, run again, close.
- **Remembers what you use.** Tables and columns your queries touched rank first in
  autocomplete and appear under *Recent* in the schema tree. Schema structure is saved per
  connection, so the tree and autocomplete are ready right after a restart (`F5` re-reads it).
- **Names quoted only when needed** (`dbt-analytics`, reserved words), with the right quote for
  the database: backticks on Databricks/Spark, MySQL and ClickHouse, brackets on SQL Server,
  double quotes elsewhere.
- **Clipboard that works.** Copy and paste go through the system clipboard (`pbcopy`/`pbpaste`,
  PowerShell on WSL, `wl-copy`, `xclip`), falling back to the terminal's OSC52 escape. `Ctrl+V`
  pastes what other programs copied.
- **History, formatting, transactions.** Searchable query history, SQL formatting,
  Auto/Manual commit with Commit/Rollback.
- **Rebindable keys, themes, command palette** (`Ctrl+P`). No AI features.

## Install

Requirements: Python 3.12+ and a Java 11+ runtime (`brew install openjdk`,
`apt install openjdk-21-jre`, ...). Check with `sqlide doctor`.

```sh
uv tool install sqlide        # or: pipx install sqlide
sqlide
```

Homebrew formula: see [packaging/homebrew](packaging/homebrew/README.md).

## Quick start

```sh
sqlide driver install postgres   # or just connect: sqlide offers to download it
sqlide                           # Ctrl+N: new connection, Enter on it: connect
```

Passwords are never written to disk. sqlide asks when you connect and keeps the password
in memory until you quit. A connection can instead read it from an environment variable
(`password_ref = "${env:PGPASSWORD}"`) or from a command such as a keychain CLI
(`password_cmd = "security find-generic-password -s mydb -w"`).

## Keys

`sqlide keys` prints every rebindable action with its default key. Override in
`~/.config/sqlide/keymap.toml`:

```toml
[keys]
"editor.run" = "f4"
```

| Action | Keys |
|---|---|
| Run statement / selection | `Ctrl+J` (= `Ctrl+Enter`), `F5` |
| Run all | `Ctrl+R`, `Shift+F5` |
| Cancel query | `Ctrl+B`, `Ctrl+F2` |
| Autocomplete | `Ctrl+Space` (opens by itself while you type a word and after a dot) |
| Format / comment | `Ctrl+L`, `F7` / `Ctrl+/` |
| Select all / copy / cut / paste | `Ctrl+A` / `Ctrl+C` / `Ctrl+X` / `Ctrl+V` |
| New connection / console / close tab | `Ctrl+N` / `Ctrl+T` / `Ctrl+W` |
| Open / save file | `Ctrl+O` / `Ctrl+S` |
| History | `Ctrl+E` |
| Switch tab | `Ctrl+PgDn` / `Ctrl+PgUp` |
| Focus connections / schema / editor / results | `Ctrl+K` / `Ctrl+D` / `Alt+Q` / `Ctrl+G` (or `F6` / `Shift+F6` to cycle) |
| Tx: toggle / commit / rollback | `F8` / `F9` / `F10` (also buttons in the toolbar) |
| Grid: sort / copy / copy as / filter / export | `s` / `Ctrl+C` / `y` / `Ctrl+F` / `e` |
| Grid: pin result / close result | `p` / `w` |
| Help: all keys, change a key | `F1` |
| Command palette | `Ctrl+P` |
| Quit | `Ctrl+Q` |

Every key is shown as it is bound *now*: the toolbar tooltips, `F1` and `sqlide keys` read
`keymap.toml`. In `F1`, `Enter` on a row asks for a new key and saves it; `Backspace` resets it.
The older Alt/F keys stay as second choices unless you rebind the action.

\* Most terminals send `Ctrl+Enter` as plain `Enter`; it only works where the terminal
speaks the kitty keyboard protocol. `Alt+Enter` is not used on purpose: it toggles
full screen in Windows Terminal.

## Files

| What | Where (Linux and WSL; macOS uses the platform equivalents) |
|---|---|
| Settings, connections, custom drivers, keymap | `~/.config/sqlide/` |
| Downloaded drivers, history, consoles | `~/.local/share/sqlide/` |
| Saved schema structure, usage counters, saved results | `meta/`, `usage.sqlite`, `results.sqlite` next to them |

Override with `SQLIDE_CONFIG_DIR` and `SQLIDE_DATA_DIR`.

## Notes

- Schema reads (tree, autocomplete) use a second connection, so they work while a query runs.
  For in-memory databases (H2 `mem:`, SQLite `:memory:`, DuckDB) a second connection would see
  a different database, so the query connection is shared and reads wait for a running query.
- Nothing polls the database. Structure is read on demand (expanding a node, autocomplete) and
  cached. After DDL in the editor the cache is dropped and the tree shows "F5 to refresh"; press
  `F5` in the tree to re-read it, also for changes made by other clients. In manual-commit mode
  new objects appear after Commit.
- MySQL `DELIMITER x` lines are understood (they are not sent to the server). On SQL Server,
  `CREATE PROCEDURE/FUNCTION/TRIGGER` without `BEGIN..END` runs up to the next `GO`, as T-SQL does.
- `Alt+1`..`Alt+4` only work in terminals with the kitty keyboard protocol; most terminals
  deliver them as Mac characters, so use the letter keys or `F6`.
- Tested on Linux and WSL against PostgreSQL, MySQL, MariaDB, ClickHouse, SQL Server, Oracle and
  H2. macOS is covered by CI. On Windows, run it inside WSL (native Windows is not supported).

## Development

```sh
uv sync
uv run pytest                 # unit, H2 integration, Textual pilot tests
uv run pytest -m docker       # also PostgreSQL in Docker
uv run ruff check && uv run pyright
```

The code is split into blocks that depend only downwards: `ui → db, sql, grid, export,
history, config → jvm, drivers`. The core never imports the UI.

## License

MIT
