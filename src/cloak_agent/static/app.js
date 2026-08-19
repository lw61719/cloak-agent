const $ = (selector) => document.querySelector(selector);

const state = {
  runId: null,
  currentUrl: "",
  status: "idle",
  lastSequence: 0,
  pollTimer: null,
  config: null,
  history: [],
};

const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
const statusLabels = {
  queued: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已停止",
};

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
if (!reduceMotion.matches) {
  document.addEventListener("pointermove", (event) => {
    document.documentElement.style.setProperty("--pointer-x", `${event.clientX}px`);
    document.documentElement.style.setProperty("--pointer-y", `${event.clientY}px`);
  }, { passive: true });
}

const labels = {
  web_run_started: ["任务已接收", "正在启动安全浏览器"],
  run_started: ["Agent 已启动", "模型正在规划下一步"],
  model_response: ["模型响应", "已完成一次决策"],
  tool_called: ["执行浏览器动作", ""],
  tool_result: ["浏览器返回结果", ""],
  tool_rejected: ["动作已拦截", "并行动作可能导致页面状态错乱"],
  run_finished: ["Agent 已完成", "已生成最终回答"],
  run_stopped: ["达到步数上限", "任务未在限制内完成"],
  web_run_finished: ["运行结束", ""],
};

function setSystem(online, text) {
  $("#systemDot").classList.toggle("online", online);
  $("#systemText").textContent = text;
}

function showError(message = "") {
  $("#formError").textContent = message;
}

function setRunStatus(status) {
  state.status = status;
  const badge = $("#runBadge");
  badge.className = `run-badge ${status}`;
  badge.textContent = status.toUpperCase();
  const running = ["queued", "running"].includes(status);
  $("#runButton").disabled = running;
  $("#cancelButton").disabled = !running;
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("配置接口不可用");
    state.config = await response.json();
    const provider = state.config.providers.find((item) => item.id === state.config.default_provider);
    $("#providerSummary").textContent = state.config.default_provider === "deepseek" ? "DeepSeek" : "OpenAI";
    $("#modelSummary").textContent = state.config.default_model;
    if (!provider?.available) showError(`${state.config.default_provider.toUpperCase()}_API_KEY 尚未配置`);
    setSystem(true, "本地服务已连接");
  } catch (error) {
    setSystem(false, "无法连接本地服务");
    showError(error.message);
  }
}

function eventDetail(event) {
  if (event.event === "tool_called") {
    const args = event.arguments ? JSON.stringify(event.arguments) : "";
    return `${event.tool || "tool"} ${args}`.trim();
  }
  if (event.event === "tool_result") {
    return event.ok ? `${event.tool || "tool"} · success` : `${event.tool || "tool"} · ${event.error_type || "error"}`;
  }
  if (event.event === "model_response") {
    const tools = event.tool_calls?.join(", ");
    return tools ? `计划调用：${tools}` : "准备输出最终回答";
  }
  if (event.status) return `状态：${event.status}`;
  return labels[event.event]?.[1] || event.event;
}

function appendEvent(event) {
  const row = document.createElement("div");
  const isTool = ["tool_called", "tool_result"].includes(event.event);
  const isError = event.ok === false || event.event === "tool_rejected";
  row.className = `event ${isTool ? "tool" : ""} ${isError ? "error" : ""}`;

  const time = new Date(event.timestamp);
  const timeText = Number.isNaN(time.getTime()) ? "--:--:--" : time.toLocaleTimeString("zh-CN", { hour12: false });
  const title = labels[event.event]?.[0] || event.event.replaceAll("_", " ");

  const timeNode = document.createElement("span");
  timeNode.className = "event-time";
  timeNode.textContent = timeText;
  const rail = document.createElement("span");
  rail.className = "event-rail";
  rail.innerHTML = '<i class="event-dot"></i>';
  const copy = document.createElement("div");
  copy.className = "event-copy";
  const strong = document.createElement("b");
  strong.textContent = title;
  const detail = document.createElement("span");
  detail.textContent = eventDetail(event);
  copy.append(strong, detail);
  row.append(timeNode, rail, copy);
  $("#timeline").append(row);
  $("#timeline").scrollTop = $("#timeline").scrollHeight;
}

function resetRunView() {
  clearTimeout(state.pollTimer);
  $("#timeline").replaceChildren();
  $("#resultCard").classList.add("hidden");
  $("#resultText").textContent = "";
  state.lastSequence = 0;
}

function showRun(run) {
  state.currentUrl = run.url || state.currentUrl;
  $("#emptyState").classList.add("hidden");
  $("#activeState").classList.remove("hidden");
  $("#runId").textContent = run.id;
  $("#runModel").textContent = `${run.provider} / ${run.model}`;
  setRunStatus(run.status);
  for (const event of run.events || []) {
    state.lastSequence = Math.max(state.lastSequence, event.sequence || 0);
    appendEvent(event);
  }
  if (run.result || run.error) {
    $("#resultCard").classList.remove("hidden");
    $("#resultText").textContent = run.result || `运行失败：${run.error}`;
  }
  if (terminalStatuses.has(run.status)) loadHistory();
}

async function pollRun() {
  if (!state.runId) return;
  try {
    const response = await fetch(`/api/runs/${state.runId}?after=${state.lastSequence}`);
    if (!response.ok) throw new Error("无法读取任务状态");
    const run = await response.json();
    showRun(run);
    if (["queued", "running"].includes(run.status)) state.pollTimer = setTimeout(pollRun, 800);
  } catch (error) {
    showError(error.message);
    setRunStatus("failed");
  }
}

function displayUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return { host: url.hostname, path: `${url.pathname}${url.search}` || "/" };
  } catch {
    return { host: rawUrl, path: "" };
  }
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function makeButton(text, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  if (className) button.className = className;
  button.addEventListener("click", onClick);
  return button;
}

function renderHistory() {
  const list = $("#historyList");
  list.replaceChildren();
  $("#historyCount").textContent = String(state.history.length);
  $("#historyEmpty").classList.toggle("hidden", state.history.length > 0);
  list.classList.toggle("hidden", state.history.length === 0);
  $("#clearHistoryButton").disabled = !state.history.some((run) => terminalStatuses.has(run.status));

  for (const run of state.history) {
    const item = document.createElement("article");
    item.className = "history-item";
    const main = document.createElement("div");
    main.className = "history-item-main";
    const copy = document.createElement("div");
    copy.className = "history-copy";
    const urlCopy = displayUrl(run.url);
    const host = document.createElement("b");
    host.textContent = urlCopy.host;
    const path = document.createElement("span");
    path.textContent = urlCopy.path;
    copy.append(host, path);
    const status = document.createElement("span");
    status.className = `history-status ${run.status}`;
    status.textContent = statusLabels[run.status] || run.status;
    main.append(copy, status);

    const meta = document.createElement("div");
    meta.className = "history-meta";
    const time = document.createElement("span");
    time.textContent = formatDate(run.created_at);
    const model = document.createElement("span");
    model.textContent = `${run.provider} / ${run.model}`;
    meta.append(time, model);

    const actions = document.createElement("div");
    actions.className = "history-actions";
    actions.append(
      makeButton("查看", "history-view", () => viewHistoricalRun(run.id)),
      makeButton("再次使用", "", () => reuseUrl(run.url)),
    );
    const source = document.createElement("a");
    source.href = run.url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = "原网页 ↗";
    actions.append(source);
    item.append(main, meta, actions);
    list.append(item);
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/runs");
    if (!response.ok) throw new Error("无法读取历史任务");
    const data = await response.json();
    state.history = data.runs || [];
    renderHistory();
  } catch (error) {
    console.warn(error.message);
  }
}

async function viewHistoricalRun(runId) {
  try {
    const response = await fetch(`/api/runs/${runId}`);
    if (!response.ok) throw new Error("该任务已经不存在");
    const run = await response.json();
    resetRunView();
    state.runId = run.id;
    $("#url").value = run.url;
    showRun(run);
    $("#historyDialog").close();
    $(".monitor").scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    if (["queued", "running"].includes(run.status)) pollRun();
  } catch (error) {
    showError(error.message);
    $("#historyDialog").close();
  }
}

function reuseUrl(url) {
  $("#url").value = url;
  $("#historyDialog").close();
  $("#url").focus();
  $("#url").select();
}

function safeFileName(url) {
  try {
    return new URL(url).hostname.replace(/[^a-z0-9.-]+/gi, "-");
  } catch {
    return "web-result";
  }
}

function exportMarkdown() {
  const result = $("#resultText").textContent.trim();
  if (!result) return;
  const content = `# 网页解析结果\n\n- 来源：${state.currentUrl || "未知"}\n- 导出时间：${new Date().toLocaleString("zh-CN")}\n\n${result}\n`;
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `${safeFileName(state.currentUrl)}-${new Date().toISOString().slice(0, 10)}.md`;
  link.click();
  URL.revokeObjectURL(objectUrl);
}

$("#runForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError();
  resetRunView();
  const payload = { url: $("#url").value.trim() };
  state.currentUrl = payload.url;

  try {
    setRunStatus("queued");
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "无法创建任务");
    state.runId = data.id;
    showRun(data);
    loadHistory();
    pollRun();
  } catch (error) {
    showError(error.message);
    setRunStatus("failed");
  }
});

$("#cancelButton").addEventListener("click", async () => {
  if (!state.runId) return;
  $("#cancelButton").disabled = true;
  try {
    const response = await fetch(`/api/runs/${state.runId}`, { method: "DELETE" });
    const run = await response.json();
    if (!response.ok) throw new Error(run.detail || "停止失败");
    showRun(run);
  } catch (error) {
    showError(error.message);
  }
});

$("#copyButton").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#resultText").textContent);
  $("#copyButton").textContent = "已复制";
  setTimeout(() => { $("#copyButton").textContent = "复制"; }, 1200);
});

$("#exportButton").addEventListener("click", exportMarkdown);
$("#openSourceButton").addEventListener("click", () => {
  if (state.currentUrl) window.open(state.currentUrl, "_blank", "noopener,noreferrer");
});

$("#sampleButton").addEventListener("click", () => {
  $("#url").value = "https://zhuanlan.zhihu.com/p/2071994707241079627";
  $("#url").focus();
});

$("#historyButton").addEventListener("click", async () => {
  await loadHistory();
  $("#historyDialog").showModal();
});
$("#closeHistoryButton").addEventListener("click", () => $("#historyDialog").close());
$("#historyDialog").addEventListener("click", (event) => {
  if (event.target === $("#historyDialog")) $("#historyDialog").close();
});
$("#clearHistoryButton").addEventListener("click", async () => {
  if (!window.confirm("确定清空所有已完成的历史任务吗？正在运行的任务会被保留。")) return;
  const response = await fetch("/api/runs", { method: "DELETE" });
  if (!response.ok) {
    showError("无法清空历史任务");
    return;
  }
  await loadHistory();
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $("#url").focus();
    $("#url").select();
  }
});

Promise.all([loadConfig(), loadHistory()]);
