const $ = (selector) => document.querySelector(selector);

const state = {
  runId: null,
  currentUrl: "",
  mode: "extract",
  status: "idle",
  lastSequence: 0,
  pollTimer: null,
  config: null,
  history: [],
  screenshotKey: "",
  approvalId: null,
};

const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
const statusLabels = {
  queued: "等待中",
  running: "运行中",
  waiting_approval: "待批准",
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
  approval_required: ["等待你的批准", "受保护操作已暂停"],
  approval_resolved: ["审批已处理", "Agent 将按照你的选择继续"],
  screenshot_captured: ["已捕获页面", "运行画面已更新"],
  screenshot_failed: ["截图失败", "不影响 Agent 继续执行"],
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

function setMode(mode) {
  state.mode = mode === "agent" ? "agent" : "extract";
  for (const button of document.querySelectorAll("[data-mode]")) {
    const active = button.dataset.mode === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  const agentMode = state.mode === "agent";
  $("#agentFields").classList.toggle("hidden", !agentMode);
  $("#extractPreset").classList.toggle("hidden", agentMode);
  $("#task").required = agentMode;
  $("#urlLabel").textContent = agentMode ? "起始网址" : "网站 URL";
  $("#runButton span").textContent = agentMode ? "运行 Agent" : "开始解析";
  showError();
}

function setRunStatus(status) {
  state.status = status;
  const badge = $("#runBadge");
  badge.className = `run-badge ${status}`;
  badge.textContent = status.toUpperCase();
  const active = ["queued", "running", "waiting_approval"].includes(status);
  $("#runButton").disabled = false;
  $("#cancelButton").disabled = !active;
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
  if (event.event === "approval_required") return event.message || "等待批准";
  if (event.event === "approval_resolved") return event.approved ? "已批准一次" : "已拒绝";
  if (event.event === "screenshot_captured") return `${event.filename || "页面截图"} · step ${event.step || "—"}`;
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
  $("#approvalCard").classList.add("hidden");
  $("#screenshotPanel").classList.add("hidden");
  $("#screenshotGallery").replaceChildren();
  state.lastSequence = 0;
  state.screenshotKey = "";
  state.approvalId = null;
}

function renderScreenshots(screenshots = []) {
  const key = screenshots.map((item) => item.filename).join("|");
  if (key === state.screenshotKey) return;
  state.screenshotKey = key;
  const gallery = $("#screenshotGallery");
  gallery.replaceChildren();
  for (const screenshot of screenshots) {
    const link = document.createElement("a");
    link.className = "screenshot-item";
    link.href = screenshot.src;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const image = document.createElement("img");
    image.src = screenshot.src;
    image.alt = `Agent 第 ${screenshot.step || "?"} 步页面截图`;
    image.loading = "lazy";
    const label = document.createElement("span");
    label.textContent = `STEP ${screenshot.step || "—"}`;
    link.append(image, label);
    gallery.append(link);
  }
  $("#screenshotCount").textContent = String(screenshots.length);
  $("#screenshotPanel").classList.toggle("hidden", screenshots.length === 0);
}

function renderApproval(approval) {
  state.approvalId = approval?.id || null;
  $("#approvalCard").classList.toggle("hidden", !approval);
  $("#approvalMessage").textContent = approval?.message || "";
  $("#approveApprovalButton").disabled = !approval;
  $("#denyApprovalButton").disabled = !approval;
}

function showRun(run) {
  state.currentUrl = run.url || state.currentUrl;
  $("#emptyState").classList.add("hidden");
  $("#activeState").classList.remove("hidden");
  $("#runId").textContent = run.id;
  $("#runModel").textContent = `${run.provider} / ${run.model}`;
  $("#runMode").textContent = `${run.mode === "agent" ? "Agent 任务" : "快速解析"} / ${run.max_steps} 步`;
  $("#runQueue").textContent = run.status === "queued" && run.queue_position
    ? `队列第 ${run.queue_position} 位`
    : (["running", "waiting_approval"].includes(run.status) ? "正在执行" : "已结束");
  $("#runTask").textContent = run.mode === "agent" ? (run.task || "Agent 任务") : "快速解析：标题、摘要与关键事实";
  $("#runUrl").textContent = run.url;
  $("#runUrl").href = run.url;
  setRunStatus(run.status);
  renderApproval(run.approval);
  renderScreenshots(run.screenshots || []);
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
    if (["queued", "running", "waiting_approval"].includes(run.status)) state.pollTimer = setTimeout(pollRun, 800);
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
    const task = document.createElement("span");
    task.className = "history-task";
    task.textContent = run.mode === "agent" ? (run.task || "Agent 任务") : "快速解析";
    copy.append(host, task);
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
      makeButton("再次使用", "", () => reuseRun(run)),
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
    restoreRunForm(run);
    showRun(run);
    $("#historyDialog").close();
    $(".monitor").scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    if (["queued", "running", "waiting_approval"].includes(run.status)) pollRun();
  } catch (error) {
    showError(error.message);
    $("#historyDialog").close();
  }
}

function restoreRunForm(run) {
  setMode(run.mode || "extract");
  $("#url").value = run.url || "";
  $("#task").value = run.mode === "agent" ? (run.task || "") : "";
  $("#maxSteps").value = String(run.max_steps || 20);
}

function reuseRun(run) {
  restoreRunForm(run);
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
  const payload = { mode: state.mode, url: $("#url").value.trim() };
  if (state.mode === "agent") {
    const task = $("#task").value.trim();
    if (!task) {
      showError("请输入 Agent 任务");
      $("#task").focus();
      return;
    }
    const maxSteps = Number($("#maxSteps").value);
    if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 60) {
      showError("最大步骤必须是 1 到 60 之间的整数");
      $("#maxSteps").focus();
      return;
    }
    payload.task = task;
    payload.max_steps = maxSteps;
  }
  resetRunView();
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

async function resolveApproval(approved) {
  if (!state.runId || !state.approvalId) return;
  const approvalId = state.approvalId;
  $("#approveApprovalButton").disabled = true;
  $("#denyApprovalButton").disabled = true;
  try {
    const response = await fetch(`/api/runs/${state.runId}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: approvalId, approved }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "审批请求已经失效");
    renderApproval(null);
    clearTimeout(state.pollTimer);
    pollRun();
  } catch (error) {
    showError(error.message);
    $("#approveApprovalButton").disabled = false;
    $("#denyApprovalButton").disabled = false;
  }
}

$("#approveApprovalButton").addEventListener("click", () => resolveApproval(true));
$("#denyApprovalButton").addEventListener("click", () => resolveApproval(false));

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

for (const button of document.querySelectorAll("[data-mode]")) {
  button.addEventListener("click", () => setMode(button.dataset.mode));
}

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

setMode("extract");
Promise.all([loadConfig(), loadHistory()]);
