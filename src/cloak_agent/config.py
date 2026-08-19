"""Configuration for the browser agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path

from .safety import ApprovalMode


class Provider(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


DEFAULT_MODELS = {
    Provider.OPENAI: "gpt-5.6-luna",
    Provider.DEEPSEEK: "deepseek-v4-flash",
}

DEFAULT_BASE_URLS = {
    Provider.OPENAI: None,
    Provider.DEEPSEEK: "https://api.deepseek.com",
}


@dataclass(slots=True)
class AgentConfig:
    provider: Provider = Provider.OPENAI
    model: str = ""
    base_url: str | None = None
    max_steps: int = 20
    headless: bool = True
    humanize: bool = True
    proxy: str | None = None
    geoip: bool = False
    locale: str | None = None
    timezone: str | None = None
    allowed_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    approval_mode: ApprovalMode = ApprovalMode.ASK
    trace_path: Path | None = None
    screenshot_dir: Path = Path("artifacts")
    page_text_limit: int = 12_000
    max_interactive_elements: int = 80

    def __post_init__(self) -> None:
        if isinstance(self.provider, str):
            self.provider = Provider(self.provider)
        if not self.model:
            env_name = f"{self.provider.value.upper()}_MODEL"
            self.model = os.getenv(env_name, DEFAULT_MODELS[self.provider])
        if self.base_url is None:
            self.base_url = DEFAULT_BASE_URLS[self.provider]
        if not 1 <= self.max_steps <= 100:
            raise ValueError("max_steps must be between 1 and 100")
        if not 1_000 <= self.page_text_limit <= 50_000:
            raise ValueError("page_text_limit must be between 1,000 and 50,000")
        if not 1 <= self.max_interactive_elements <= 200:
            raise ValueError("max_interactive_elements must be between 1 and 200")
        self.allowed_domains = tuple(
            domain.strip().lower().lstrip(".")
            for domain in self.allowed_domains
            if domain.strip()
        )

    @property
    def api_key_env(self) -> str:
        return f"{self.provider.value.upper()}_API_KEY"
