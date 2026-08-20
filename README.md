# Cloak Browser Agent

一个基于 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) 和 Responses API 的受控浏览器 Agent，支持 OpenAI 与 DeepSeek。它直接调用 CloakBrowser 的异步 Playwright 接口，保留源码级浏览器指纹处理与 `humanize=True` 行为层，同时为 Agent 增加动作审批、域名白名单、私网拦截、最大步数和 JSONL 审计日志。

## 能做什么

- 打开网页、读取可见文本和交互控件
- 点击、输入、选择下拉项、滚动、返回、等待
- 按需保存整页截图
- 通过自然语言完成检索、比价、资料收集和网页 QA 等任务
- 在付款、删除、发布、发送、上传、敏感字段输入前请求人工审批

本项目不会破解 CAPTCHA，也不应被用于未授权访问、批量注册、撞库或规避网站访问控制。请遵守目标网站条款与适用法律。

## 安装

需要 Python 3.10+。建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

第一次实际启动时，CloakBrowser 会从其官方渠道下载浏览器二进制文件。最新版本可能需要 CloakBrowser license key；可以运行 `cloakbrowser login`，或设置 `CLOAKBROWSER_LICENSE_KEY`。

项目启动时会自动读取当前目录下的 `.env`，且不会覆盖终端中已经设置的环境变量。可以先复制模板：

```powershell
Copy-Item .env.example .env
```

使用 OpenAI 时在 `.env` 中设置：

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.6-luna
```

使用 DeepSeek 时在 `.env` 中设置：

```dotenv
CLOAK_AGENT_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-v4-flash
```

## 运行

```powershell
cloak-agent "打开 https://example.com，告诉我页面标题和主要内容"
```

## Web 控制台

启动本地网站：

```powershell
cloak-agent-web
```

然后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。Web 控制台支持两种模式：默认的“快速解析”只需输入 URL，继续使用固定提示词提取页面标题、主要内容、关键事实和原始地址；“Agent 任务”可以额外输入自然语言任务，并将最大步骤设置为 1–60（默认 20）。两种模式都会从起始 URL 生成站点域名白名单，本阶段不允许 Agent 任意跨域访问。

Provider 和模型由 `.env` 决定。网页可以查看实时工具轨迹、运行参数和自动页面截图，也可以取消任务、复制或导出 Markdown 结果。多个任务会按提交顺序进入单浏览器 FIFO 队列；在付款、删除、发布、上传或敏感字段输入前，任务会暂停并等待当前 Web 用户明确批准或拒绝，批准只对本次操作生效。API key 只从服务器 `.env` 读取，不会返回给浏览器，私网目标仍始终阻止。

“最近任务”支持回看或恢复 URL、模式、任务和最大步骤，最多保留 20 条进程内记录；历史、队列和截图在服务重启后清空。按 `Ctrl/Command + K` 可以快速聚焦网址输入框。

更换端口：

```powershell
cloak-agent-web --port 8080
```

## 部署到 Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/lw61719/cloak-agent)

项目根目录包含 `Dockerfile` 和 `render.yaml`，使用 CloakBrowser 官方 Docker 镜像，在 Render 新加坡区域运行单个 Free Web Service。服务器没有固定月费；浏览器任务仍会消耗所配置模型的 API 额度。免费实例闲置 15 分钟后会休眠，下次访问通常需要约一分钟唤醒，休眠、重新部署或重启都会清空内存中的任务历史。

1. 将项目提交并推送到 GitHub、GitLab 或 Bitbucket。不要提交 `.env`。
2. 在 Render 控制台选择 **New → Blueprint**，连接代码仓库并部署根目录的 `render.yaml`。
3. 首次创建时填写两个 Secret：
   - `DEEPSEEK_API_KEY`：DeepSeek API Key。
   - `CLOAK_AGENT_ACCESS_PASSWORD`：网站访问密码，建议使用至少 20 位随机字符串。
4. 部署完成后打开 Render 提供的 `onrender.com` 地址，浏览器会要求输入用户名 `cloak` 和上一步设置的密码。

健康检查路径是 `/healthz`，它不需要认证且不返回配置或密钥。线上服务强制单实例、单 Uvicorn worker，避免同一内存任务被分发到不同进程。任务历史和运行状态仍保存在实例内存中，重新部署或重启后会清空。

如果使用新版或付费 CloakBrowser Binary，在 Render Secrets 中另行加入 `CLOAKBROWSER_LICENSE_KEY`。若准备把网站开放给第三方用户，而不只是自己或团队内部使用，上线前需要确认 CloakBrowser Binary License 是否覆盖该服务模式。

使用 DeepSeek：

```powershell
cloak-agent "打开 https://example.com，告诉我页面标题和主要内容" `
  --provider deepseek
```

默认使用 `deepseek-v4-flash`，也可以指定模型：

```powershell
cloak-agent "完成资料收集任务" `
  --provider deepseek `
  --model deepseek-v4-pro
```

显示浏览器窗口并限制在指定站点：

```powershell
cloak-agent "在站内搜索 browser automation 并总结前三项" `
  --headed `
  --allow-domain example.com
```

使用代理并让时区、语言和 WebRTC 地址匹配代理出口：

```powershell
cloak-agent "完成我的资料收集任务" `
  --proxy "http://user:pass@host:port" `
  --geoip
```

主要选项：

- `--provider`：`openai`（默认）或 `deepseek`，也可通过 `CLOAK_AGENT_PROVIDER` 指定
- `--model`：OpenAI 默认 `gpt-5.6-luna`，DeepSeek 默认 `deepseek-v4-flash`；也可用对应的 `OPENAI_MODEL` / `DEEPSEEK_MODEL` 指定
- `--base-url`：覆盖 Provider API 地址；DeepSeek 默认 `https://api.deepseek.com`
- `--max-steps`：模型-工具循环上限，默认 20
- `--approval ask|deny|allow`：危险动作处理方式，默认交互询问
- `--allow-domain`：域名白名单，可重复传入
- `--allow-private-network`：允许访问本机或内网，默认关闭
- `--trace`：指定 JSONL 审计文件；默认写入 `logs/`
- `--no-humanize`：关闭 CloakBrowser 的人类化交互层

也可以用 `CLOAK_AGENT_PROXY` 设置默认代理，避免复用系统级代理变量造成意外路由。

## 安全边界

默认策略有意保守：

1. 只允许 HTTP(S)，阻止 URL 内嵌凭证及私网/本机地址。
2. 页面内容被明确标记为不可信数据，Agent 不应执行网页中的提示注入指令。
3. 付款、购买、转账、删除、发送、发布、上传等控制需要审批。
4. 密码、验证码、银行卡和文件输入需要审批，审计日志不记录任务正文、输入正文或最终回答。
5. 浏览器动作串行执行，并有最大步数；工具错误会显式返回给模型。

如果在无交互环境中使用 `--approval ask`，需要审批的动作会被拒绝。只有在任务和目标站点都可信时才应使用 `--approval allow`。

## 测试

```powershell
pytest -q
```

单元测试不需要 API key 或下载浏览器；真实端到端运行需要所选 Provider 的 API key 和可用的 CloakBrowser 二进制许可。

## 许可说明

本项目只把 `cloakbrowser` 列为依赖，不分发其浏览器二进制。CloakBrowser 的 Python 包装层是 MIT License，但下载的浏览器 Binary 使用 CloakHQ 自己的 Binary License。根据上游当前条款，内部使用通常允许；重新分发、嵌入第三方产品、对外提供浏览器能力或 SaaS 可能需要单独授权。上线前请自行复核上游最新许可。
