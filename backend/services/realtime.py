"""Realtime fan-out over WebSockets.

Backs the in-app notification bell and the messaging widget. Replaces the
30-second polling loop the frontend used to run for the unread-count badge
and the chat-contacts list.

Connection model
----------------
* One websocket per browser tab. A single user can have many tabs open
  (school admin watching activity + student dashboard + teacher gradebook),
  so we keep a list of sockets per ``user_id``.
* On connect, the client passes a JWT in the ``?token=`` query string.
  We validate it via the same auth_backend used elsewhere — no second
  identity surface.
* The server sends ``{"type": "ready"}`` once auth is good. Any later
  failure (token expiry, etc.) ends the socket with code 1008.
* The client may send ``{"type": "ping"}``; the server replies with
  ``{"type": "pong"}``. We don't rely on this for liveness — it exists
  only to keep intermediaries from killing idle sockets.

Event types pushed to the browser
---------------------------------
* ``notification.created`` ``{ user_id }`` — new notification persisted.
  Frontend invalidates its notifications + unread-count queries.
* ``notification.read``    ``{ user_id, id? }`` — one or all marked read.
* ``chat.message``         ``{ user_id, from_user_id }`` — new inbound
  message. Frontend invalidates chat-contacts + the specific thread key.
* ``chat.read``            ``{ user_id, other_id }`` — recipient read
  the messages we sent. Frontend re-fetches chat-contacts to clear the
  "unread by them" indicator we may display in the future.

Failure mode
------------
If a broadcast can't serialize or a socket has already closed, we log
and continue. Caller paths never block on realtime fan-out.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class RealtimeHub:
    """In-process per-user socket registry.

    Lives as a module-level singleton (``hub``) so route handlers can
    fire-and-forget broadcasts without plumbing the instance around.

    For a single-process FastAPI deployment this is all we need. If we
    ever shard across workers we'd front this with Redis pub/sub — the
    public API (``broadcast_to_user``) stays the same.
    """

    def __init__(self) -> None:
        # user_id -> list of open WebSocket connections
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, []).append(ws)

    async def unregister(self, user_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            try:
                conns.remove(ws)
            except ValueError:
                pass
            if not conns:
                self._connections.pop(user_id, None)

    def count_for(self, user_id: str) -> int:
        return len(self._connections.get(user_id, []))

    async def broadcast_to_user(self, user_id: str, event: Dict[str, Any]) -> None:
        """Send `event` to every open socket for `user_id`.

        Best-effort: sockets that have closed are dropped silently. A
        single failing socket never blocks delivery to the others.
        """
        if not user_id:
            return
        sockets: List[WebSocket]
        async with self._lock:
            sockets = list(self._connections.get(user_id, []))
        if not sockets:
            return

        dead: List[WebSocket] = []
        payload = dict(event)
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except (WebSocketDisconnect, RuntimeError) as e:
                # RuntimeError fires when sending on an already-closed
                # socket; treat both as "this socket is gone."
                logger.debug("Realtime: dropping closed socket: %s", e)
                dead.append(ws)
            except Exception:  # noqa: BLE001
                logger.exception("Realtime: send failed for user %s", user_id)
                dead.append(ws)

        if dead:
            async with self._lock:
                conns = self._connections.get(user_id)
                if conns:
                    for ws in dead:
                        try:
                            conns.remove(ws)
                        except ValueError:
                            pass
                    if not conns:
                        self._connections.pop(user_id, None)


# Module-level singleton. Routes do `from services.realtime import hub`.
hub = RealtimeHub()


# ── Convenience emitters used by main.py route handlers ─────────────────


async def emit_notification_created(user_id: Optional[str]) -> None:
    if not user_id:
        return
    await hub.broadcast_to_user(str(user_id), {
        "type": "notification.created",
        "user_id": str(user_id),
    })


async def emit_notification_read(user_id: Optional[str], notification_id: Optional[str] = None) -> None:
    if not user_id:
        return
    payload: Dict[str, Any] = {
        "type": "notification.read",
        "user_id": str(user_id),
    }
    if notification_id:
        payload["id"] = notification_id
    await hub.broadcast_to_user(str(user_id), payload)


async def emit_chat_message(to_user_id: Optional[str], from_user_id: Optional[str]) -> None:
    """Notify the recipient that they have a new inbound message."""
    if not to_user_id:
        return
    await hub.broadcast_to_user(str(to_user_id), {
        "type": "chat.message",
        "user_id": str(to_user_id),
        "from_user_id": str(from_user_id) if from_user_id else None,
    })


async def emit_chat_read(to_user_id: Optional[str], other_user_id: Optional[str]) -> None:
    """Tell `to_user_id` that `other_user_id` read their messages."""
    if not to_user_id:
        return
    await hub.broadcast_to_user(str(to_user_id), {
        "type": "chat.read",
        "user_id": str(to_user_id),
        "other_id": str(other_user_id) if other_user_id else None,
    })
