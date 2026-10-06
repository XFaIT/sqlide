"""Shared helpers for the UI tests."""

from textual.widgets import RichLog

from sqlide.ui.widgets.result_grid import ResultGrid


async def wait_for(pilot, cond, timeout=15.0):
    for _ in range(int(timeout / 0.05)):
        if cond():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met in time")


def console(app):
    return app.screen.console


async def connect_first(pilot, app):
    """Select the first saved connection in the sidebar and wait until it is connected."""
    await pilot.pause()
    app.screen.sidebar.index = 0
    await pilot.press("enter")
    await wait_for(pilot, lambda: console(app).session is not None)


def grids(app):
    return list(app.screen.query(ResultGrid))


def log_text(app) -> str:
    log = app.screen.query_one("#log", RichLog)
    return "\n".join(line.text for line in log.lines)
