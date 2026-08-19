from cloak_agent.cli import build_parser, configure_console_encoding, load_environment


def test_dotenv_selects_deepseek(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "CLOAK_AGENT_PROVIDER=deepseek\n"
        "DEEPSEEK_API_KEY=test-key\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLOAK_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    load_environment()
    args = build_parser().parse_args(["browse example.com"])

    assert args.provider == "deepseek"


def test_dotenv_does_not_override_shell_environment(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "CLOAK_AGENT_PROVIDER=deepseek\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLOAK_AGENT_PROVIDER", "openai")

    load_environment()
    args = build_parser().parse_args(["browse example.com"])

    assert args.provider == "openai"


def test_console_encoding_configuration_is_supported() -> None:
    configure_console_encoding()
