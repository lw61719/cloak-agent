"""LLM provider client creation shared by CLI and web entry points."""

from __future__ import annotations

import os

from openai import AsyncOpenAI

from .config import AgentConfig


class ProviderConfigError(RuntimeError):
    """Raised when a selected provider is missing required configuration."""


def create_provider_client(config: AgentConfig) -> AsyncOpenAI:
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise ProviderConfigError(f"{config.api_key_env} is not set")
    kwargs: dict[str, str] = {"api_key": api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return AsyncOpenAI(**kwargs)
