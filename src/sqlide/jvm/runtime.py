"""Start the in-process JVM exactly once (JPype cannot restart it)."""

from __future__ import annotations

import threading

import jpype
import jpype.config

from sqlide.jvm.locate import JvmInfo, locate_jvm

# Databricks (and other Arrow based) drivers read result sets through java.nio internals;
# on Java 17+ without --add-opens the query is sent but fetching the result hangs or fails.
JVM_ARGS = (
    "-Djava.awt.headless=true",
    "--add-opens=java.base/java.nio=ALL-UNNAMED",
    "-Dio.netty.tryReflectionSetAccessible=true",
)

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
            jpype.startJVM(str(info.libjvm), *JVM_ARGS, convertStrings=False)
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
