"""RHUserRepository — CRUD for rh_users table."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models import RHUserModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class RHUserRepository:

    async def create(
        self,
        email: str,
        hashed_password: str,
        full_name: Optional[str] = None,
        role: str = "recruiter",
    ) -> RHUserModel:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                user = RHUserModel(
                    email=email,
                    hashed_password=hashed_password,
                    full_name=full_name,
                    role=role,
                )
                session.add(user)
            await session.refresh(user)
            return user

    async def get_by_id(self, user_id: int) -> Optional[RHUserModel]:
        async with AsyncSessionLocal() as session:
            return await session.get(RHUserModel, user_id)

    async def get_by_email(self, email: str) -> Optional[RHUserModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RHUserModel).where(RHUserModel.email == email)
            )
            return result.scalar_one_or_none()

    async def update_password(self, user_id: int, hashed_password: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                user = await session.get(RHUserModel, user_id)
                if user:
                    user.hashed_password = hashed_password

    async def deactivate(self, user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                user = await session.get(RHUserModel, user_id)
                if user:
                    user.is_active = False

    async def delete(self, user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                user = await session.get(RHUserModel, user_id)
                if user:
                    await session.delete(user)
        logger.info("[RHUserRepo] Deleted user %s", user_id)
