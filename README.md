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
  completion, keywords and functions per dialect.
- **Consoles and files.** Tabs with their own connection; consoles autosave and come back
  after a restart; open and save `.sql` files (`sqlide a.sql b.sql`).
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
| Run statement / selection | `F5`, `Ctrl+J`, `Ctrl+Enter`\* |
| Run all | `Shift+F5` |
| Cancel query | `Ctrl+F2` |
| Autocomplete | `Ctrl+Space` (opens by itself after a dot) |
| Format / comment | `F7` or `Ctrl+Alt+L` / `Ctrl+/` or `Alt+/` |
| New connection / console / close tab | `Ctrl+N` / `Ctrl+T` / `Alt+W` |
| Open / save file | `Ctrl+O` / `Ctrl+S` |
| History | `Alt+E` |
| Switch tab | `Alt+←` `Alt+→` |
| Focus connections / schema / editor / results | `Alt+C` / `Alt+D` / `Alt+Q` / `Alt+R` (or `F6` / `Shift+F6` to cycle) |
| Tx: toggle / commit / rollback | `F8` / `F9` / `F10` |
| Grid: sort / copy / copy as / filter / export | `s` / `Ctrl+C` / `y` / `/` / `e` |
| Command palette | `Ctrl+P` |
| Quit | `Ctrl+Q` |

\* Most terminals send `Ctrl+Enter` as plain `Enter`; it only works where the terminal
speaks the kitty keyboard protocol. `Alt+Enter` is not used on purpose: it toggles
full screen in Windows Terminal.

## Files

| What | Where (Linux; macOS and Windows use the platform equivalents) |
|---|---|
| Settings, connections, custom drivers, keymap | `~/.config/sqlide/` |
| Downloaded drivers, history, consoles | `~/.local/share/sqlide/` |

Override with `SQLIDE_CONFIG_DIR` and `SQLIDE_DATA_DIR`.

## Notes

- Schema reads (tree, autocomplete) use a second connection, so they work while a query runs.
  For in-memory databases (H2 `mem:`, SQLite `:memory:`, DuckDB) a second connection would see
  a different database, so the query connection is shared and reads wait for a running query.
- Autocomplete reads cached metadata. DDL you run in the editor refreshes it; changes made by
  other clients need `F5` in the schema tree. In manual-commit mode new objects appear after
  Commit.
- MySQL `DELIMITER x` lines are understood (they are not sent to the server). On SQL Server,
  `CREATE PROCEDURE/FUNCTION/TRIGGER` without `BEGIN..END` runs up to the next `GO`, as T-SQL does.
- `Alt+1`..`Alt+4` only work in terminals with the kitty keyboard protocol; most terminals
  deliver them as Mac characters, so use the letter keys or `F6`.
- Tested on Linux and WSL against PostgreSQL, MySQL, MariaDB, ClickHouse, SQL Server, Oracle and
  H2. macOS is covered by CI; native Windows is best effort (use WSL).

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
