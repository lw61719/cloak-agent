from fastapi.testclient import TestClient

from cloak_agent.web import RunManager, RunRequest, WebRun, _site_domain, app, build_fixed_task


client = TestClient(app)


def test_web_home_and_assets_load() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Cloak Browser Agent" in response.text
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


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
        task="second task",
        provider="deepseek",
        model="deepseek-chat",
        status="running",
    )

    assert [run["id"] for run in history.recent()] == ["second", "first"]
    assert history.clear_finished() == 1
    assert list(history.runs) == ["second"]


def test_run_history_api_has_no_secret_configuration() -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert "runs" in response.json()
    assert "api_key" not in response.text.lower()
