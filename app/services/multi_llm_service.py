"""
multi_llm_service.py
====================
Service LLM utilisant le proxy Orange LiteLLM (compatible OpenAI).
Base URL : https://management.llmproxy.ai.orange
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
import httpx
from openai import AsyncOpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)


class MultiLLMService:
    """
    Service LLM basé sur le proxy Orange LiteLLM.
    Compatible OpenAI — supporte tous les modèles disponibles sur le proxy :
      openai/gpt-4o-mini  (défaut — rapide et performant)
      openai/gpt-4o       (plus puissant)
      vertex_ai/claude-sonnet-4-6  (Claude via Vertex)
      etc.
    """

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_base_url,
            http_client=httpx.AsyncClient(verify=False, timeout=120.0),
        )
        self._model = settings.litellm_model
        logger.info(
            "[LLM] Orange proxy initialisé — base_url=%s  model=%s",
            settings.litellm_base_url,
            self._model,
        )

        # Rétro-compatibilité avec le code qui lit .providers / .failed_providers
        self.providers: dict = {"orange": self._call_orange}
        self.failed_providers: set[str] = set()
        self.last_successful_provider: Optional[str] = "orange"

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 3000,
        force_french: bool = False,
        conversation_history: list[dict] | None = None,
    ) -> Dict[str, Any]:
        """
        Génère une réponse via le proxy Orange LiteLLM.

        Args:
            prompt:               Message courant de l'utilisateur.
            system_prompt:        Instruction système.
            temperature:          Température de génération (0-1).
            max_tokens:           Nombre maximum de tokens.
            force_french:         Injecte une règle pour forcer le français.
            conversation_history: Historique [{role, content}] pour la continuité.

        Returns:
            {"content": "...", "provider": "orange", "success": True}
        """
        if force_french:
            fr_rule = "RÈGLE ABSOLUE: Tu dois répondre UNIQUEMENT ET ENTIÈREMENT EN FRANÇAIS, quelle que soit la langue du message ci-dessus."
            system_prompt = (system_prompt + "\n\n" + fr_rule).strip()
            prompt = prompt + "\n\n⚠️ RÉPONDS EXCLUSIVEMENT EN FRANÇAIS."

        messages = self._build_messages(system_prompt, conversation_history, prompt)

        try:
            content = await self._call_orange(messages, temperature, max_tokens)
            return {"content": content, "provider": "orange", "success": True}
        except Exception as exc:
            logger.error("[LLM] Erreur Orange proxy: %s", exc)
            raise

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_messages(
        self,
        system_prompt: str,
        conversation_history: list[dict] | None,
        current_prompt: str,
    ) -> list[dict]:
        """
        Construit le tableau de messages pour l'API chat :
          [system] + [hist_user, hist_assistant, ...] + [current_user]
        """
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role")
                content = str(msg.get("content", ""))
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content[:2000]})
        messages.append({"role": "user", "content": current_prompt})
        return messages

    # ── Provider ──────────────────────────────────────────────────────────────

    async def _call_orange(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Appel au proxy Orange LiteLLM."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    def reset_failed_providers(self):
        """No-op — gardé pour rétro-compatibilité."""
        pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_llm_service_instance: Optional[MultiLLMService] = None


def get_llm_service() -> MultiLLMService:
    """Retourne l'instance singleton du service LLM."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = MultiLLMService()
    return _llm_service_instance
