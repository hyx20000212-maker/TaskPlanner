"""
LLM Client — Abstraction over OpenAI-compatible APIs.
Supports DeepSeek, OpenAI, and any OpenAI-compatible endpoint.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


# ── Default configurations for popular providers ────────────────────

@dataclass
class ProviderConfig:
    name: str
    base_url: str
    default_model: str


PROVIDERS: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
    ),
    "openai": ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    ),
}


class LLMClient:
    """Thin wrapper around the OpenAI SDK for structured JSON task analysis.

    Usage:
        client = LLMClient(api_key="sk-...", provider="deepseek")
        result = client.chat_json(system_prompt="...", user_prompt="...")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        """
        Args:
            api_key: API key. If None, reads from env: DEEPSEEK_API_KEY or OPENAI_API_KEY.
            provider: "deepseek" or "openai", or custom.
            model: Model name. If None, uses provider default.
            base_url: Custom API base URL. If None, uses provider default.
            temperature: Sampling temperature (0.0-2.0). Lower = more deterministic.
            max_tokens: Maximum tokens in the response.
        """
        self.provider = provider

        # Resolve API key
        if api_key is None:
            api_key = self._resolve_api_key(provider)
        if not api_key:
            raise ValueError(
                f"No API key found. Set {'DEEPSEEK_API_KEY' if provider == 'deepseek' else 'OPENAI_API_KEY'} "
                f"environment variable, or pass api_key explicitly."
            )

        # Resolve base URL and model
        provider_cfg = PROVIDERS.get(provider)
        if base_url is None and provider_cfg:
            base_url = provider_cfg.base_url
        if model is None and provider_cfg:
            model = provider_cfg.default_model
        if not model:
            model = "deepseek-chat"

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _resolve_api_key(provider: str) -> Optional[str]:
        """Try to find API key from environment variables."""
        if provider == "deepseek":
            return os.environ.get("DEEPSEEK_API_KEY")
        elif provider == "openai":
            return os.environ.get("OPENAI_API_KEY")
        # Try both
        return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """Send a chat completion request and parse the response as JSON.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message with the task description.

        Returns:
            Parsed JSON dict from the LLM response.

        Raises:
            ValueError: If response cannot be parsed as JSON.
            RuntimeError: If API call fails.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},  # Force JSON output
            )
        except Exception as e:
            raise RuntimeError(f"LLM API call failed: {e}") from e

        content = response.choices[0].message.content or "{}"

        # Parse JSON, stripping markdown fences if present
        content = content.strip()
        if content.startswith("```"):
            # Remove ```json ... ``` or just ``` ... ```
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse LLM response as JSON. Raw response:\n{content[:500]}..."
            ) from e

        # Inject metadata
        data["_meta"] = {
            "model": self.model,
            "tokens_used": response.usage.total_tokens if response.usage else 0,
        }

        return data


def detect_provider_from_key(api_key: str) -> str:
    """Guess the provider from API key prefix."""
    if api_key.startswith("sk-"):
        # DeepSeek and OpenAI both use sk- prefix. Try DeepSeek first as default.
        return "deepseek"
    return "openai"
