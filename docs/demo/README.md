# README demos

The GIFs in `docs/img` are recordings of the real application:

```sh
uv run python docs/demo/record.py            # drives sqlide in tmux, writes docs/demo/*.cast
agg --font-family "DejaVu Sans Mono" --font-size 16 --idle-time-limit 2 \
    docs/demo/query.cast docs/img/query.gif   # https://github.com/asciinema/agg
```

`seed.py` builds the demo database (H2 file with a `dbt-analytics` schema). Needs tmux,
`agg` and the H2 driver in `tests/.cache` (run the test suite once to download it).
