"""NotificationRepository — CRUD for notifications table."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, update

from app.infrastructure.database.models import NotificationModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class NotificationRepository:

    async def create(
        self,
        user_id: int,
        title: str,
        body: Optional[str] = None,
        link: Optional[str] = None,
    ) -> NotificationModel:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                notif = NotificationModel(
                    user_id=user_id,
                    title=title,
                    body=body,
                    link=link,
                    is_read=False,
                )
                session.add(notif)
            await session.refresh(notif)
            return notif

    async def get_unread(self, user_id: int, limit: int = 50) -> list[NotificationModel]:
        """Uses the partial index ix_notifications_unread for efficiency."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(NotificationModel)
                .where(
                    NotificationModel.user_id == user_id,
                    NotificationModel.is_read == False,  # noqa: E712 — SQLAlchemy requires ==
                )
                .order_by(NotificationModel.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars())

    async def get_all(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(NotificationModel)
                .where(NotificationModel.user_id == user_id)
                .order_by(NotificationModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars())

    async def mark_read(self, notification_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(NotificationModel)
                    .where(NotificationModel.id == notification_id)
                    .values(is_read=True)
                )

    async def mark_all_read(self, user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(NotificationModel)
                    .where(
                        NotificationModel.user_id == user_id,
                        NotificationModel.is_read == False,  # noqa: E712
                    )
                    .values(is_read=True)
                )

    async def count_unread(self, user_id: int) -> int:
        from sqlalchemy import func, select as sa_select
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                sa_select(func.count()).where(
                    NotificationModel.user_id == user_id,
                    NotificationModel.is_read == False,  # noqa: E712
                )
            )
            return result.scalar_one()
