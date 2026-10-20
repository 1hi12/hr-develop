"""
WebSocket connection manager — channel-based broadcast.

Clients subscribe to named channels (e.g. "cv_processing", "job_<job_id>").
pg_notify listener calls broadcast_to_channel(); individual status pushes use
send_to_client() for targeted messages.
"""

import logging
from collections import defaultdict
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# client_id → WebSocket
_connections: dict[str, WebSocket] = {}

# channel → set of client_ids subscribed to that channel
_subscriptions: dict[str, set[str]] = defaultdict(set)


# ── Connection lifecycle ───────────────────────────────────────────────────

async def register_connection(client_id: str, websocket: WebSocket) -> None:
    _connections[client_id] = websocket
    logger.info("[WS] Connected: %s", client_id)


async def unregister_connection(client_id: str) -> None:
    _connections.pop(client_id, None)
    # Remove from every channel it was subscribed to
    for subscribers in _subscriptions.values():
        subscribers.discard(client_id)
    logger.info("[WS] Disconnected: %s", client_id)


# ── Channel subscription ───────────────────────────────────────────────────

def subscribe(client_id: str, channel: str) -> None:
    _subscriptions[channel].add(client_id)
    logger.debug("[WS] %s subscribed to channel '%s'", client_id, channel)


def unsubscribe(client_id: str, channel: str) -> None:
    _subscriptions[channel].discard(client_id)


# ── Message delivery ───────────────────────────────────────────────────────

async def send_to_client(client_id: str, data: dict) -> None:
    """Send a message to a single client."""
    ws = _connections.get(client_id)
    if ws:
        try:
            await ws.send_json(data)
        except Exception as exc:
            logger.warning("[WS] Send failed for %s: %s", client_id, exc)
            await unregister_connection(client_id)


async def broadcast_to_channel(channel: str, data: dict) -> None:
    """Broadcast a message to every client subscribed to *channel*.

    Called by the pg_notify listener and any other server-side event producer.
    Disconnected clients are cleaned up silently.
    """
    subscribers = list(_subscriptions.get(channel, set()))
    if not subscribers:
        logger.debug("[WS] No subscribers on channel '%s'", channel)
        return

    dead: list[str] = []
    for client_id in subscribers:
        ws = _connections.get(client_id)
        if ws is None:
            dead.append(client_id)
            continue
        try:
            await ws.send_json(data)
        except Exception as exc:
            logger.warning("[WS] Broadcast to %s failed: %s", client_id, exc)
            dead.append(client_id)

    for client_id in dead:
        await unregister_connection(client_id)


async def broadcast_to_all(data: dict) -> None:
    """Broadcast to every connected client regardless of channel."""
    for client_id in list(_connections.keys()):
        await send_to_client(client_id, data)


# ── Legacy shim (preserved for existing callers in ingest_task.py) ─────────

async def send_progress(client_id: str, data: dict) -> None:
    """Targeted push to a single client — kept for backward compatibility."""
    await send_to_client(client_id, data)
