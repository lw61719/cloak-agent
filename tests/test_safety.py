import pytest

from cloak_agent.browser import CloakBrowserTools
from cloak_agent.config import AgentConfig
from cloak_agent.safety import ApprovalMode, SafetyError, SafetyPolicy


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "https://user:pass@example.com/",
    ],
)
def test_unsafe_urls_are_blocked(url: str) -> None:
    with pytest.raises(SafetyError):
        SafetyPolicy().validate_url(url)


def test_allowlist_accepts_domain_and_subdomain() -> None:
    policy = SafetyPolicy(allowed_domains=("example.com",))
    assert policy.validate_url("https://example.com/")
    assert policy.validate_url("https://docs.example.com/guide")
    with pytest.raises(SafetyError):
        policy.validate_url("https://example.net/")


def test_consequential_click_requires_approval() -> None:
    denied = SafetyPolicy(approval_mode=ApprovalMode.DENY)
    with pytest.raises(SafetyError):
        denied.authorize_click("Pay now")

    allowed = SafetyPolicy(approval_mode=ApprovalMode.ALLOW)
    allowed.authorize_click("Pay now")


def test_sensitive_input_uses_callback() -> None:
    prompts: list[str] = []
    policy = SafetyPolicy(
        approval_mode=ApprovalMode.ASK,
        approval_callback=lambda message: prompts.append(message) is None,
    )
    policy.authorize_input("Account password", "password")
    assert prompts and "sensitive field" in prompts[0]


@pytest.mark.asyncio
async def test_async_web_approval_callback_is_awaited() -> None:
    prompts: list[str] = []

    async def approve(message: str) -> bool:
        prompts.append(message)
        return True

    policy = SafetyPolicy(
        approval_mode=ApprovalMode.ASK,
        approval_callback=approve,
    )

    await policy.authorize_click_async("Pay now")

    assert prompts and "consequential control" in prompts[0]


@pytest.mark.asyncio
async def test_async_web_approval_can_be_denied() -> None:
    async def deny(message: str) -> bool:
        return False

    policy = SafetyPolicy(
        approval_mode=ApprovalMode.ASK,
        approval_callback=deny,
    )

    with pytest.raises(SafetyError, match="User did not approve"):
        await policy.authorize_input_async("Account password", "password")


@pytest.mark.asyncio
async def test_screenshots_are_blocked_after_sensitive_input() -> None:
    tools = CloakBrowserTools(AgentConfig(), SafetyPolicy())
    tools.page = object()
    tools._sensitive_input_used = True

    with pytest.raises(SafetyError, match="disabled after sensitive data"):
        await tools.screenshot("sensitive.png")
