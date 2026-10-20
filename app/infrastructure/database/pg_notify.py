"""
PostgreSQL LISTEN/NOTIFY listener for CV processing events.

PostgreSQL sends a notification on channel 'cv_processing' when a
cv_files row changes status. This listener wakes up and logs the event.
Extend handle_notification() to trigger downstream actions (e.g. webhooks).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import asyncpg

from app.config.settings import settings

logger = logging.getLogger(__name__)

_CHANNEL = "cv_processing"


class CVProcessingListener:
    """
    Async pg_notify listener.
    Start with await listener.start()
    Stop  with await listener.stop()
    """

    def __init__(self) -> None:
        self._conn: Optional[asyncpg.Connection] = None
        self._task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._conn = await asyncpg.connect(settings.database_url_asyncpg)
        await self._conn.add_listener(_CHANNEL, self._on_notification)
        self._task = asyncio.create_task(self._keepalive(), name="pg_notify_keepalive")
        logger.info("[pg_notify] Listening on channel '%s'", _CHANNEL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._conn:
            try:
                await self._conn.remove_listener(_CHANNEL, self._on_notification)
                await self._conn.close()
            except Exception as e:
                logger.warning("[pg_notify] Error during shutdown: %s", e)

        logger.info("[pg_notify] Listener stopped")

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_notification(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Called by asyncpg on every NOTIFY."""
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {"raw": payload}

        logger.info("[pg_notify] channel=%s pid=%s payload=%s", channel, pid, data)
        asyncio.create_task(self.handle_notification(channel, data))

    async def handle_notification(self, channel: str, data: dict) -> None:
        """
        Override or extend this method to react to CV status changes.
        Example payload: {"candidate_id": "...", "status": "done"}
        """
        candidate_id = data.get("candidate_id", "unknown")
        status       = data.get("status", "unknown")
        logger.info(
            "[pg_notify] CV event — candidate=%s status=%s",
            candidate_id, status,
        )

    async def _keepalive(self) -> None:
        """Sends a periodic SELECT 1 to keep the asyncpg connection alive."""
        while True:
            await asyncio.sleep(30)
            try:
                if self._conn:
                    await self._conn.execute("SELECT 1")
            except Exception as e:
                logger.warning("[pg_notify] Keepalive failed: %s", e)
