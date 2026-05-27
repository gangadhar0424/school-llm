"""Silence noisy Windows-only asyncio socket-shutdown errors.

On Windows, Streamlit's event loop uses asyncio.ProactorEventLoop. When the
remote peer closes a connection abruptly (browser tab closed mid-request,
backend restarted, antivirus interception, etc.), the loop calls
``_ProactorBasePipeTransport._call_connection_lost`` which then tries
``socket.shutdown(SHUT_RDWR)`` on an already-dead socket. Windows raises
``ConnectionResetError [WinError 10054]`` from that shutdown — the
connection IS reset, asyncio is just complaining that it couldn't politely
close a socket the OS already closed.

The error is purely cosmetic — nothing functional breaks — but it spams the
terminal whenever a user refreshes a Streamlit page or the backend bounces.
The standard fix (documented in cpython tracker bpo-39010 and widely
mirrored on Stack Overflow) is to wrap the offending method to swallow the
``ConnectionResetError`` from this specific cleanup path.

Importing this module is enough — it patches on import, guarded by a flag
so re-import (Streamlit reruns the script on every interaction) is a
no-op.
"""
from __future__ import annotations

import sys

_PATCH_FLAG = "_school_llm_proactor_silenced"


def _install() -> None:
    # Only relevant on Windows; on POSIX the proactor module is unused.
    if not sys.platform.startswith("win"):
        return

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
    except Exception:
        return

    if getattr(_ProactorBasePipeTransport, _PATCH_FLAG, False):
        return

    original = _ProactorBasePipeTransport._call_connection_lost

    def _silent_call_connection_lost(self, exc):  # type: ignore[no-untyped-def]
        try:
            original(self, exc)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            # The remote already closed; nothing to clean up.
            pass

    _ProactorBasePipeTransport._call_connection_lost = _silent_call_connection_lost
    setattr(_ProactorBasePipeTransport, _PATCH_FLAG, True)


_install()
