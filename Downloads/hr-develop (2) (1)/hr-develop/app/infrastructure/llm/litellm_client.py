"""
LiteLLM Proxy Client - Remplacement de Gemini par OpenAI via Orange LiteLLM Proxy
Utilise l'API OpenAI standard mais pointe vers le proxy Orange
"""

from __future__ import annotations

import json
import logging
from typing import Any

import openai
from openai import OpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Client pour LiteLLM Proxy (compatible OpenAI API)"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        """
        Initialise le client LiteLLM

        Args:
            api_key: Clé API (défaut: depuis settings)
            base_url: URL du proxy (défaut: depuis settings)
            model: Modèle à utiliser (défaut: depuis settings.litellm_model)
            temperature: Température pour la génération (0.0-1.0)
            max_tokens: Nombre maximum de tokens
        """
        self.api_key = api_key or settings.litellm_api_key
        self.base_url = base_url or settings.litellm_base_url
        self.model = model or settings.litellm_model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialiser le client OpenAI pointant vers LiteLLM Proxy
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        logger.info(
            f"[LiteLLMClient] Initialized with model={self.model}, "
            f"base_url={self.base_url}, temp={self.temperature}"
        )

    def generate_content(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Génère du contenu avec le modèle LLM

        Args:
            prompt: Prompt utilisateur
            system_prompt: Prompt système (optionnel)
            temperature: Override temperature (optionnel)
            max_tokens: Override max_tokens (optionnel)

        Returns:
            Texte généré par le modèle
        """
        messages = []

        # Ajouter le system prompt si fourni
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Ajouter le prompt utilisateur
        messages.append({
            "role": "user",
            "content": prompt
        })

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            content = response.choices[0].message.content
            logger.debug(f"[LiteLLMClient] Generated {len(content)} chars")

            return content

        except Exception as e:
            logger.error(f"[LiteLLMClient] Error generating content: {e}")
            raise

    def generate_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        Génère une réponse JSON structurée

        Args:
            prompt: Prompt utilisateur
            system_prompt: Prompt système (optionnel)
            temperature: Override temperature (optionnel)
            max_tokens: Override max_tokens (optionnel)

        Returns:
            Dictionnaire JSON parsé
        """
        # Ajouter instruction pour retourner JSON
        enhanced_prompt = f"{prompt}\n\nReturn your response as valid JSON only, without any markdown formatting or code blocks."

        if system_prompt:
            system_prompt = f"{system_prompt}\n\nYou must respond with valid JSON only."

        content = self.generate_content(
            prompt=enhanced_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Parser le JSON
        try:
            # Essayer de parser directement
            return json.loads(content)
        except json.JSONDecodeError:
            # Si échec, essayer d'extraire JSON des markdown code blocks
            logger.warning("[LiteLLMClient] Direct JSON parse failed, trying extraction")

            # Extraire JSON entre ```json et ``` ou ``` et ```
            import re

            # Pattern 1: ```json\n{...}\n```
            pattern1 = r'```json\s*(\{.*?\})\s*```'
            match = re.search(pattern1, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            # Pattern 2: ```\n{...}\n```
            pattern2 = r'```\s*(\{.*?\})\s*```'
            match = re.search(pattern2, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            # Pattern 3: Trouver premier { et dernier }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    pass

            # Si tout échoue, logger et raise
            logger.error(f"[LiteLLMClient] Failed to parse JSON: {content[:200]}...")
            raise ValueError(f"Could not parse JSON from response: {content[:200]}...")

    async def agenerate_content(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Version asynchrone de generate_content

        Note: OpenAI Python SDK supporte async nativement
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        try:
            # Utiliser le client async d'OpenAI
            from openai import AsyncOpenAI

            async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

            response = await async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            content = response.choices[0].message.content
            logger.debug(f"[LiteLLMClient] Generated {len(content)} chars (async)")

            return content

        except Exception as e:
            logger.error(f"[LiteLLMClient] Error generating content (async): {e}")
            raise

    async def agenerate_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Version asynchrone de generate_json"""

        enhanced_prompt = f"{prompt}\n\nReturn your response as valid JSON only, without any markdown formatting or code blocks."

        if system_prompt:
            system_prompt = f"{system_prompt}\n\nYou must respond with valid JSON only."

        content = await self.agenerate_content(
            prompt=enhanced_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Utiliser la même logique de parsing que generate_json
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("[LiteLLMClient] Direct JSON parse failed (async), trying extraction")

            import re

            # Mêmes patterns que la version sync
            pattern1 = r'```json\s*(\{.*?\})\s*```'
            match = re.search(pattern1, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            pattern2 = r'```\s*(\{.*?\})\s*```'
            match = re.search(pattern2, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    pass

            logger.error(f"[LiteLLMClient] Failed to parse JSON (async): {content[:200]}...")
            raise ValueError(f"Could not parse JSON from response: {content[:200]}...")


# Singleton global (optionnel, pour réutilisation)
_global_client: LiteLLMClient | None = None


def get_litellm_client() -> LiteLLMClient:
    """Récupère une instance singleton du client LiteLLM"""
    global _global_client

    if _global_client is None:
        _global_client = LiteLLMClient()

    return _global_client
