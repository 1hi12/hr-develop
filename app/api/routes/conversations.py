"""
conversations.py
================
API endpoints pour la gestion des conversations de l'AI Assistant
"""

from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from app.infrastructure.repositories.conversation_repo import ConversationRepository
from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["AI Assistant - Conversations"])


# ═══════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════

class MessageSchema(BaseModel):
    """Schéma pour un message"""
    id: str
    role: str  # 'user' | 'assistant'
    content: str
    timestamp: str
    recommendations: Optional[dict] = None


class ConversationResponse(BaseModel):
    """Schéma de réponse pour une conversation"""
    conversation_id: str
    user_id: int
    title: str
    messages: List[dict]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Schéma de réponse pour la liste des conversations"""
    conversations: List[ConversationResponse]
    total: int


class CreateConversationRequest(BaseModel):
    """Requête pour créer une conversation"""
    title: str = Field(..., description="Titre de la conversation", max_length=512)


class UpdateConversationRequest(BaseModel):
    """Requête pour mettre à jour une conversation"""
    title: Optional[str] = Field(None, description="Nouveau titre", max_length=512)
    messages: Optional[List[dict]] = Field(None, description="Messages mis à jour")


class AddMessageRequest(BaseModel):
    """Requête pour ajouter un message"""
    message: dict = Field(..., description="Message à ajouter")


# ═══════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════

@router.get("/", response_model=ConversationListResponse)
async def get_user_conversations(
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0
):
    """
    📋 Récupérer toutes les conversations de l'utilisateur connecté
    """
    try:
        repo = ConversationRepository()
        conversations = await repo.get_user_conversations(
            user_id=current_user["id"],
            limit=limit,
            offset=offset
        )
        
        conversation_responses = [
            ConversationResponse(
                conversation_id=conv.conversation_id,
                user_id=conv.user_id,
                title=conv.title,
                messages=conv.messages or [],
                created_at=conv.created_at,
                updated_at=conv.updated_at
            )
            for conv in conversations
        ]
        
        return ConversationListResponse(
            conversations=conversation_responses,
            total=len(conversation_responses)
        )
        
    except Exception as e:
        logger.error(f"[API] Erreur lors de la récupération des conversations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des conversations: {str(e)}"
        )


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    ➕ Créer une nouvelle conversation
    """
    try:
        logger.info(f"[API] Création conversation pour user {current_user['id']}: '{request.title}'")
        
        repo = ConversationRepository()
        conversation = await repo.create_conversation(
            user_id=current_user["id"],
            title=request.title,
            messages=[]
        )
        
        logger.info(f"[API] Conversation créée avec ID: {conversation.conversation_id}")
        
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            title=conversation.title,
            messages=conversation.messages or [],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at
        )
        
    except Exception as e:
        logger.error(f"[API] Erreur lors de la création de conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de conversation: {str(e)}"
        )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    🔍 Récupérer une conversation par ID
    """
    try:
        repo = ConversationRepository()
        conversation = await repo.get_conversation_by_id(
            conversation_id=conversation_id,
            user_id=current_user["id"]
        )
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation non trouvée"
            )
        
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            title=conversation.title,
            messages=conversation.messages or [],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Erreur lors de la récupération de conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération de conversation: {str(e)}"
        )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    ✏️ Mettre à jour une conversation
    """
    try:
        repo = ConversationRepository()
        conversation = await repo.update_conversation(
            conversation_id=conversation_id,
            user_id=current_user["id"],
            title=request.title,
            messages=request.messages
        )
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation non trouvée"
            )
        
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            title=conversation.title,
            messages=conversation.messages or [],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Erreur lors de la mise à jour de conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour de conversation: {str(e)}"
        )


@router.post("/{conversation_id}/messages", response_model=ConversationResponse)
async def add_message(
    conversation_id: str,
    request: AddMessageRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    💬 Ajouter un message à une conversation
    """
    try:
        logger.info(f"[API] Ajout message à conversation {conversation_id} pour user {current_user['id']}")
        
        repo = ConversationRepository()
        conversation = await repo.add_message_to_conversation(
            conversation_id=conversation_id,
            user_id=current_user["id"],
            message=request.message
        )
        
        if not conversation:
            logger.warning(f"[API] Conversation {conversation_id} non trouvée pour user {current_user['id']}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation non trouvée"
            )
        
        logger.info(f"[API] Message ajouté avec succès. Total messages: {len(conversation.messages or [])}")
        
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            title=conversation.title,
            messages=conversation.messages or [],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Erreur lors de l'ajout de message à {conversation_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'ajout de message: {str(e)}"
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    🗑️ Supprimer une conversation
    """
    try:
        repo = ConversationRepository()
        deleted = await repo.delete_conversation(
            conversation_id=conversation_id,
            user_id=current_user["id"]
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation non trouvée"
            )
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Erreur lors de la suppression de conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression de conversation: {str(e)}"
        )
