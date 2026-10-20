"""
ai_memory_service.py
====================
Mémoire persistante de l'assistant IA par utilisateur (Redis, TTL 30 jours).

Stocke les contextes des projets/analyses récents afin que l'assistant puisse
référencer les discussions passées même dans une nouvelle conversation.

Clé Redis : ai:memory:{user_id}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config.settings import settings

logger = logging.getLogger(__name__)

MEMORY_TTL = 30 * 86_400   # 30 jours
MAX_CONTEXTS = 5            # Garder les 5 analyses les plus récentes


def _memory_key(user_id: int) -> str:
    return f"ai:memory:{user_id}"


async def _get_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# ── Écriture ──────────────────────────────────────────────────────────────────

async def save_project_context(
    user_id: int,
    project_name: str,
    top_candidates: list[str],   # ex: ["John Doe (87%)", "Jane Smith (82%)"]
    tasks: list[str],            # ex: ["API REST", "Base de données"]
    conversation_id: str,
) -> None:
    """
    Sauvegarde le contexte d'un projet analysé dans la mémoire utilisateur.
    Insère en tête de liste, garde au plus MAX_CONTEXTS entrées.
    """
    try:
        client = await _get_client()
        async with client:
            key = _memory_key(user_id)
            raw = await client.get(key)
            memories: list[dict] = json.loads(raw) if raw else []

            # Éviter les doublons sur le même projet dans la même journée
            memories = [m for m in memories if m.get("project_name") != project_name]

            memories.insert(0, {
                "project_name": project_name,
                "analyzed_at": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
                "top_candidates": top_candidates[:5],
                "tasks": tasks[:6],
                "conversation_id": conversation_id,
            })
            memories = memories[:MAX_CONTEXTS]

            await client.set(key, json.dumps(memories, ensure_ascii=False), ex=MEMORY_TTL)
            logger.info("[AIMemory] Projet '%s' sauvegardé pour user %d", project_name, user_id)
    except Exception as exc:
        logger.warning("[AIMemory] save_project_context failed: %s", exc)


# ── Lecture ───────────────────────────────────────────────────────────────────

async def get_user_memory_prompt(user_id: int) -> str:
    """
    Retourne un bloc Markdown décrivant les projets récemment analysés,
    prêt à être injecté en préfixe du system prompt.

    Retourne une chaîne vide s'il n'y a aucune mémoire.
    """
    try:
        client = await _get_client()
        async with client:
            raw = await client.get(_memory_key(user_id))
            if not raw:
                return ""
            memories: list[dict] = json.loads(raw)
            if not memories:
                return ""

            lines = ["## Historique des analyses récentes de ce recruteur :"]
            for m in memories:
                line = f"- **{m['project_name']}** ({m.get('analyzed_at', '?')})"
                if m.get("top_candidates"):
                    line += f" — Top candidats : {', '.join(m['top_candidates'])}"
                if m.get("tasks"):
                    line += f" — Tâches : {', '.join(m['tasks'])}"
                lines.append(line)
            lines.append("")
            return "\n".join(lines)
    except Exception as exc:
        logger.warning("[AIMemory] get_user_memory_prompt failed: %s", exc)
        return ""


async def get_raw_memories(user_id: int) -> list[dict]:
    """Retourne la liste brute des mémoires (pour usage programmatique)."""
    try:
        client = await _get_client()
        async with client:
            raw = await client.get(_memory_key(user_id))
            return json.loads(raw) if raw else []
    except Exception as exc:
        logger.warning("[AIMemory] get_raw_memories failed: %s", exc)
        return []
