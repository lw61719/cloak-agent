from cloak_agent.config import AgentConfig, Provider


def test_openai_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    config = AgentConfig()
    assert config.provider is Provider.OPENAI
    assert config.model == "gpt-5.6-luna"
    assert config.base_url is None
    assert config.api_key_env == "OPENAI_API_KEY"


def test_deepseek_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    config = AgentConfig(provider=Provider.DEEPSEEK)
    assert config.model == "deepseek-v4-flash"
    assert config.base_url == "https://api.deepseek.com"
    assert config.api_key_env == "DEEPSEEK_API_KEY"


def test_provider_model_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    config = AgentConfig(provider="deepseek")
    assert config.provider is Provider.DEEPSEEK
    assert config.model == "deepseek-v4-pro"
