"""
conversation_repo.py
====================
Repository pour la gestion des conversations de l'AI Assistant
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models import ConversationModel

logger = logging.getLogger(__name__)


class ConversationRepository:
    """Repository pour gérer les conversations de l'AI Assistant"""
    
    async def create_conversation(
        self,
        user_id: int,
        title: str,
        messages: List[dict] = None
    ) -> ConversationModel:
        """Créer une nouvelle conversation"""
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        
        async with AsyncSessionLocal() as session:
            conversation = ConversationModel(
                conversation_id=conversation_id,
                user_id=user_id,
                title=title,
                messages=messages or []
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            
            logger.info(f"[ConversationRepo] Nouvelle conversation créée: {conversation_id} pour user {user_id}")
            return conversation
    
    async def get_conversation_by_id(
        self,
        conversation_id: str,
        user_id: int
    ) -> Optional[ConversationModel]:
        """Récupérer une conversation par ID (avec vérification user)"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationModel).where(
                    ConversationModel.conversation_id == conversation_id,
                    ConversationModel.user_id == user_id
                )
            )
            return result.scalar_one_or_none()
    
    async def get_user_conversations(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[ConversationModel]:
        """Récupérer toutes les conversations d'un utilisateur"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationModel)
                .where(ConversationModel.user_id == user_id)
                .order_by(desc(ConversationModel.updated_at))
                .limit(limit)
                .offset(offset)
            )
            conversations = result.scalars().all()
            logger.info(f"[ConversationRepo] {len(conversations)} conversations trouvées pour user {user_id}")
            return list(conversations)
    
    async def update_conversation(
        self,
        conversation_id: str,
        user_id: int,
        title: Optional[str] = None,
        messages: Optional[List[dict]] = None
    ) -> Optional[ConversationModel]:
        """Mettre à jour une conversation"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationModel).where(
                    ConversationModel.conversation_id == conversation_id,
                    ConversationModel.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
            
            if title is not None:
                conversation.title = title
            if messages is not None:
                conversation.messages = messages
            
            conversation.updated_at = datetime.utcnow()
            
            await session.commit()
            await session.refresh(conversation)
            
            logger.info(f"[ConversationRepo] Conversation {conversation_id} mise à jour")
            return conversation
    
    async def add_message_to_conversation(
        self,
        conversation_id: str,
        user_id: int,
        message: dict
    ) -> Optional[ConversationModel]:
        """Ajouter un message à une conversation"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationModel).where(
                    ConversationModel.conversation_id == conversation_id,
                    ConversationModel.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
            
            # Ajouter le message
            messages = conversation.messages or []
            messages.append(message)
            conversation.messages = messages
            conversation.updated_at = datetime.utcnow()
            
            # Utiliser flag pour forcer l'update du JSONB
            from sqlalchemy.orm import attributes
            attributes.flag_modified(conversation, "messages")
            
            await session.commit()
            await session.refresh(conversation)
            
            logger.info(f"[ConversationRepo] Message ajouté à {conversation_id}")
            return conversation
    
    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: int
    ) -> bool:
        """Supprimer une conversation"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(ConversationModel).where(
                    ConversationModel.conversation_id == conversation_id,
                    ConversationModel.user_id == user_id
                )
            )
            await session.commit()
            
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"[ConversationRepo] Conversation {conversation_id} supprimée")
            else:
                logger.warning(f"[ConversationRepo] Conversation {conversation_id} non trouvée pour suppression")
            
            return deleted
    
    async def delete_all_user_conversations(
        self,
        user_id: int
    ) -> int:
        """Supprimer toutes les conversations d'un utilisateur"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(ConversationModel).where(
                    ConversationModel.user_id == user_id
                )
            )
            await session.commit()
            
            count = result.rowcount
            logger.info(f"[ConversationRepo] {count} conversations supprimées pour user {user_id}")
            return count
