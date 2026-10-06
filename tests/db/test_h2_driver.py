"""Real end-to-end: H2 from Maven Central loaded through our loader. Needs network once."""

import jpype


def test_driver_loaded(h2):
    defn, loaded = h2
    assert defn.class_name == "org.h2.Driver"
    assert str(loaded.driver.getClass().getName()) == "org.h2.Driver"


async def test_session_open_reports_product(session):
    assert "H2" in session.product and session.connected
    assert jpype.isJVMStarted()
