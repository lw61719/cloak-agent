from types import SimpleNamespace

import pytest

from cloak_agent.agent import (
    AgentLimitError,
    BrowserAgent,
    TOOL_SCHEMAS,
    tool_schemas_for_provider,
)
from cloak_agent.config import Provider
from cloak_agent.trace import TraceLogger


class FakeBrowserTools:
    def __init__(self) -> None:
        self.calls = []
        self.screenshots = []

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"ok": True, "url": arguments.get("url", "https://example.com")}

    async def screenshot(self, filename):
        self.screenshots.append(filename)
        return {
            "ok": True,
            "path": f"artifacts/{filename}",
            "url": "https://example.com",
        }

    async def capture_preview(self, filename):
        return await self.screenshot(filename)


class FakeResponses:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self._responses)


def fake_response(*items, text="", response_id="resp_test"):
    return SimpleNamespace(output=list(items), output_text=text, id=response_id)


def tool_call(
    name="navigate",
    arguments='{"url":"https://example.com"}',
    call_id="call_1",
):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=arguments,
        call_id=call_id,
    )


@pytest.mark.asyncio
async def test_agent_executes_tool_then_returns_final_text() -> None:
    responses = FakeResponses(
        [fake_response(tool_call()), fake_response(text="Finished with evidence.")]
    )
    client = SimpleNamespace(responses=responses)
    tools = FakeBrowserTools()
    agent = BrowserAgent(client, tools, model="test-model", max_steps=2)

    answer = await agent.run("Open example.com")

    assert answer == "Finished with evidence."
    assert tools.calls == [("navigate", {"url": "https://example.com"})]
    continuation = responses.requests[1]["input"][-1]
    assert continuation["type"] == "function_call_output"
    assert continuation["call_id"] == "call_1"


@pytest.mark.asyncio
async def test_agent_stops_at_step_limit() -> None:
    responses = FakeResponses([fake_response(tool_call())])
    client = SimpleNamespace(responses=responses)
    agent = BrowserAgent(client, FakeBrowserTools(), model="test-model", max_steps=1)
    with pytest.raises(AgentLimitError):
        await agent.run("Keep browsing forever")


def test_all_tool_schemas_are_strict() -> None:
    for tool in TOOL_SCHEMAS:
        assert tool["strict"] is True
        assert tool["parameters"]["additionalProperties"] is False
        assert set(tool["parameters"]["properties"]) == set(
            tool["parameters"]["required"]
        )


def test_deepseek_schemas_use_stable_non_beta_mode() -> None:
    tools = tool_schemas_for_provider(Provider.DEEPSEEK)
    assert all("strict" not in tool for tool in tools)
    assert all(tool.get("strict") is True for tool in TOOL_SCHEMAS)


@pytest.mark.asyncio
async def test_parallel_browser_calls_only_execute_first() -> None:
    first = tool_call(call_id="call_1")
    second = tool_call(
        name="wait",
        arguments='{"seconds":1}',
        call_id="call_2",
    )
    responses = FakeResponses(
        [fake_response(first, second), fake_response(text="Finished safely.")]
    )
    client = SimpleNamespace(responses=responses)
    tools = FakeBrowserTools()
    agent = BrowserAgent(
        client,
        tools,
        model="deepseek-v4-flash",
        provider=Provider.DEEPSEEK,
        max_steps=2,
    )

    assert await agent.run("Browse") == "Finished safely."
    assert tools.calls == [("navigate", {"url": "https://example.com"})]
    outputs = responses.requests[1]["input"][-2:]
    assert outputs[1]["call_id"] == "call_2"
    assert "parallel_browser_action_rejected" in outputs[1]["output"]


@pytest.mark.asyncio
async def test_web_agent_captures_screenshot_after_browser_action() -> None:
    responses = FakeResponses(
        [fake_response(tool_call()), fake_response(text="Finished safely.")]
    )
    events = []
    tools = FakeBrowserTools()
    agent = BrowserAgent(
        SimpleNamespace(responses=responses),
        tools,
        model="test-model",
        max_steps=2,
        trace=TraceLogger(None, event_sink=events.append),
        capture_screenshots=True,
    )

    assert await agent.run("Browse") == "Finished safely."
    assert tools.screenshots == ["step-01-navigate.png"]
    screenshot_event = next(
        event for event in events if event["event"] == "screenshot_captured"
    )
    assert screenshot_event["filename"] == "step-01-navigate.png"
