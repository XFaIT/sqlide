"""Start the in-process JVM exactly once (JPype cannot restart it)."""

from __future__ import annotations

import threading

import jpype
import jpype.config

from sqlide.jvm.locate import JvmInfo, locate_jvm

_lock = threading.Lock()
_info: JvmInfo | None = None


def ensure_jvm() -> JvmInfo:
    """Idempotent and thread-safe. Raises JvmNotFound with an install hint."""
    global _info
    with _lock:
        if _info is not None:
            return _info
        info = locate_jvm()
        if not jpype.isJVMStarted():
            # We start the JVM from worker threads; DestroyJavaVM at interpreter exit then
            # hangs. Sessions are closed explicitly, so skipping the JVM teardown loses nothing.
            jpype.config.destroy_jvm = False
            jpype.startJVM(str(info.libjvm), "-Djava.awt.headless=true", convertStrings=False)
            _silence_jvm_streams()
        _info = info
        return info


def jvm_started() -> bool:
    return jpype.isJVMStarted()


def _silence_jvm_streams() -> None:
    """Drivers (SLF4J etc.) print straight to the JVM's fd 1/2, which would corrupt the TUI."""
    System = jpype.JClass("java.lang.System")
    sink = jpype.JClass("java.io.PrintStream")(
        jpype.JClass("java.io.OutputStream").nullOutputStream()
    )
    System.setOut(sink)
    System.setErr(sink)
