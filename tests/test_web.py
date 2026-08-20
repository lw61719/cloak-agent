import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cloak_agent.safety import ApprovalMode
from cloak_agent.web import (
    RunManager,
    RunRequest,
    WebRun,
    _build_web_agent_config,
    _site_domain,
    app,
    build_agent_task,
    build_fixed_task,
    manager as web_manager,
)


client = TestClient(app)


def test_web_home_and_assets_load() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Cloak Browser Agent" in response.text
    assert "快速解析" in response.text
    assert "Agent 任务" in response.text
    assert 'id="task"' in response.text
    assert 'id="maxSteps"' in response.text
    assert 'href="/static/styles.css?v=0.2.2"' in response.text
    assert 'src="/static/app.js?v=0.2.2"' in response.text
    styles = client.get("/static/styles.css?v=0.2.2")
    script = client.get("/static/app.js?v=0.2.2")
    assert styles.status_code == 200
    assert script.status_code == 200
    assert styles.headers["cache-control"] == "no-cache"
    assert script.headers["cache-control"] == "no-cache"


def test_health_check_does_not_require_authentication(monkeypatch) -> None:
    monkeypatch.setenv("CLOAK_AGENT_ACCESS_PASSWORD", "production-secret")
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_production_password_protects_site_and_api(monkeypatch) -> None:
    monkeypatch.setenv("CLOAK_AGENT_ACCESS_USERNAME", "owner")
    monkeypatch.setenv("CLOAK_AGENT_ACCESS_PASSWORD", "production-secret")

    assert client.get("/").status_code == 401
    assert client.get("/api/config").status_code == 401
    response = client.get("/api/config", auth=("owner", "production-secret"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_public_config_never_exposes_api_keys() -> None:
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload["providers"]} == {"openai", "deepseek"}
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "sk-" not in serialized


def test_invalid_run_is_rejected_without_starting_browser() -> None:
    response = client.post(
        "/api/runs",
        json={"url": "file:///etc/passwd"},
    )
    assert response.status_code == 422


def test_unknown_run_returns_404() -> None:
    assert client.get("/api/runs/not-found").status_code == 404


def test_url_only_request_and_fixed_prompt() -> None:
    request = RunRequest(url="zhuanlan.zhihu.com/p/123")
    assert request.url == "https://zhuanlan.zhihu.com/p/123"
    task = build_fixed_task(request.url)
    assert "页面准确标题" in task
    assert request.url in task
    assert _site_domain(request.url) == "zhihu.com"


@pytest.mark.asyncio
async def test_extract_mode_uses_fixed_task(monkeypatch) -> None:
    manager = RunManager()

    async def skip_execution(run: WebRun, request: RunRequest) -> None:
        return None

    monkeypatch.setattr(manager, "_execute", skip_execution)
    request = RunRequest(url="https://example.com/article")
    run = manager.start(request)
    await run.worker

    assert run.mode == "extract"
    assert run.task is None
    assert run.execution_task == build_fixed_task(request.url)


@pytest.mark.asyncio
async def test_agent_mode_accepts_custom_task(monkeypatch) -> None:
    manager = RunManager()

    async def skip_execution(run: WebRun, request: RunRequest) -> None:
        return None

    monkeypatch.setattr(manager, "_execute", skip_execution)
    request = RunRequest(
        url="https://example.com",
        mode="agent",
        task="  进入 pricing 页面并总结 Pro 套餐  ",
    )
    run = manager.start(request)
    await run.worker

    assert run.mode == "agent"
    assert run.task == "进入 pricing 页面并总结 Pro 套餐"
    assert run.execution_task == build_agent_task(request.url, request.task)
    assert request.url in run.execution_task
    assert "来源 URL" in run.execution_task


def test_agent_mode_requires_task() -> None:
    with pytest.raises(ValidationError, match="task is required"):
        RunRequest(url="https://example.com", mode="agent")


def test_agent_mode_rejects_blank_task() -> None:
    with pytest.raises(ValidationError, match="task is required"):
        RunRequest(url="https://example.com", mode="agent", task="   \n")


def test_max_steps_defaults_to_20() -> None:
    assert RunRequest(url="https://example.com").max_steps == 20


def test_max_steps_accepts_valid_value() -> None:
    request = RunRequest(
        url="https://example.com",
        mode="agent",
        task="检查定价",
        max_steps=37,
    )
    assert request.max_steps == 37


def test_max_steps_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        RunRequest(url="https://example.com", max_steps=0)


def test_max_steps_rejects_over_60() -> None:
    with pytest.raises(ValidationError):
        RunRequest(url="https://example.com", max_steps=61)


def test_existing_url_validation_still_works() -> None:
    with pytest.raises(ValidationError):
        RunRequest(url="file:///etc/passwd")


def test_agent_web_mode_remains_domain_restricted() -> None:
    request = RunRequest(
        url="https://docs.example.com/pricing",
        mode="agent",
        task="检查价格",
        max_steps=12,
    )
    run = WebRun(
        id="agent-run",
        url=request.url,
        provider="deepseek",
        model="deepseek-chat",
        mode="agent",
        task=request.task,
        max_steps=request.max_steps,
    )

    config = _build_web_agent_config(run, request)

    assert config.allowed_domains == ("example.com",)
    assert config.max_steps == 12
    assert config.headless is True
    assert config.humanize is True
    assert config.approval_mode is ApprovalMode.ASK
    assert config.allow_private_network is False


def test_site_domain_handles_compound_public_suffix() -> None:
    assert _site_domain("https://news.example.com.cn/story") == "example.com.cn"


def test_run_history_is_recent_first_and_clearable() -> None:
    history = RunManager()
    history.runs["first"] = WebRun(
        id="first",
        url="https://example.com/first",
        task="first task",
        provider="deepseek",
        model="deepseek-chat",
        status="completed",
        result="first result",
    )
    history.runs["second"] = WebRun(
        id="second",
        url="https://example.com/second",
        provider="deepseek",
        model="deepseek-chat",
        mode="agent",
        task="second task",
        max_steps=42,
        execution_task="internal execution prompt",
        status="running",
    )

    recent = history.recent()
    assert [run["id"] for run in recent] == ["second", "first"]
    assert recent[0]["mode"] == "agent"
    assert recent[0]["task"] == "second task"
    assert recent[0]["max_steps"] == 42
    assert "execution_task" not in recent[0]
    assert "execution_task" not in history.runs["second"].public()
    assert history.clear_finished() == 1
    assert list(history.runs) == ["second"]


def test_run_history_api_has_no_secret_configuration() -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()
    assert "api_key" not in response.text.lower()


@pytest.mark.asyncio
async def test_run_manager_executes_queued_tasks_in_fifo_order(monkeypatch) -> None:
    manager = RunManager()
    started: asyncio.Queue[str] = asyncio.Queue()
    gates: dict[str, asyncio.Event] = {}

    async def controlled_execution(run: WebRun, request: RunRequest) -> None:
        run.status = "running"
        gate = asyncio.Event()
        gates[run.id] = gate
        started.put_nowait(run.id)
        await gate.wait()
        run.status = "completed"

    monkeypatch.setattr(manager, "_execute", controlled_execution)
    first = manager.start(RunRequest(url="https://example.com/first"))
    second = manager.start(RunRequest(url="https://example.com/second"))

    assert await asyncio.wait_for(started.get(), timeout=1) == first.id
    assert second.status == "queued"
    assert second.queue_position == 1

    gates[first.id].set()
    await first.worker
    assert await asyncio.wait_for(started.get(), timeout=1) == second.id
    gates[second.id].set()
    await second.worker

    assert first.status == "completed"
    assert second.status == "completed"


@pytest.mark.asyncio
async def test_web_run_waits_for_and_resolves_approval() -> None:
    manager = RunManager()
    run = WebRun(
        id="approval-run",
        url="https://example.com",
        provider="deepseek",
        model="deepseek-chat",
        mode="agent",
        task="执行受保护操作",
    )
    manager.runs[run.id] = run

    waiting = asyncio.create_task(run.request_approval("Click publish"))
    await asyncio.sleep(0)
    approval_id = run.pending_approval["id"]

    assert run.status == "waiting_approval"
    assert manager.resolve_approval(run.id, approval_id, True) is run
    assert await waiting is True
    assert run.status == "running"
    assert run.pending_approval is None
    assert any(event["event"] == "approval_resolved" for event in run.events)


def test_web_run_public_data_includes_safe_screenshot_metadata() -> None:
    run = WebRun(
        id="screenshot-run",
        url="https://example.com",
        provider="deepseek",
        model="deepseek-chat",
    )
    run.push_event(
        {
            "timestamp": "2026-08-20T00:00:00+00:00",
            "event": "screenshot_captured",
            "step": 2,
            "filename": "step-02-click.png",
            "url": "https://example.com/pricing",
        }
    )

    screenshot = run.public()["screenshots"][0]
    assert screenshot["filename"] == "step-02-click.png"
    assert screenshot["src"].endswith(
        "/api/runs/screenshot-run/screenshots/step-02-click.png"
    )


def test_screenshot_api_serves_only_known_run_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    run = WebRun(
        id="served-screenshot",
        url="https://example.com",
        provider="deepseek",
        model="deepseek-chat",
    )
    web_manager.runs[run.id] = run
    screenshot = Path("artifacts") / run.id / "step-01-navigate.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        response = client.get(
            f"/api/runs/{run.id}/screenshots/{screenshot.name}"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert client.get(
            f"/api/runs/{run.id}/screenshots/missing.png"
        ).status_code == 404
    finally:
        web_manager.runs.pop(run.id, None)


def test_event_sequences_remain_monotonic_after_history_trimming() -> None:
    run = WebRun(
        id="long-run",
        url="https://example.com",
        provider="deepseek",
        model="deepseek-chat",
    )
    for index in range(260):
        run.push_event({"timestamp": str(index), "event": "test_event"})

    assert len(run.events) == 250
    assert run.events[0]["sequence"] == 11
    assert run.events[-1]["sequence"] == 260
