<div align="center">

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/mascot.gif" width="120" alt="AemeathCode 吉祥物">

# AemeathCode

**一个从零手搓的 Coding Agent —— 既是能跑的终端 AI Agent,也是一趟看得见的系统工程学习历程。**

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/Nijikasuki/AemeathCode/blob/main/LICENSE)
[![Built with asyncio](https://img.shields.io/badge/built%20with-asyncio-blue)](https://docs.python.org/3/library/asyncio.html)
[![TUI: Textual](https://img.shields.io/badge/TUI-Textual-5A5AFF)](https://textual.textualize.io/)
[![MCP](https://img.shields.io/badge/MCP-client-orange)](https://modelcontextprotocol.io/)
[![CI](https://github.com/Nijikasuki/AemeathCode/actions/workflows/ci.yml/badge.svg)](https://github.com/Nijikasuki/AemeathCode/actions/workflows/ci.yml)

**简体中文** · [English](https://github.com/Nijikasuki/AemeathCode/blob/main/README_EN.md)

</div>

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/splash.png" width="100%" alt="AemeathCode TUI 启动后的界面">

<sub>左栏 Status / Sessions / Thinking · 中间 Content 和输入行 · 右栏 Tasks / Changes / MCP / Skills。</sub>

---

## 它是什么

给它一个目标,它自己规划步骤、读写文件、执行命令、观察结果,循环推进直到做完 —— 全程在终端里看得见。

它由两个进程组成:前台界面和后台常驻的 daemon,中间是一条自己实现的多路复用协议。ReAct 循环、工具注册表、会话记忆、权限审批、上下文压缩、子 agent、MCP 客户端,全部用纯 Python + asyncio 从零写,没有用任何 agent 框架。

这是一个学习与展示型项目。它能真实执行 shell 命令、真实写文件 —— 请在你信任的目录里跑(见[安全声明](#安全声明))。

---

## 装上,跑起来

支持 Linux / macOS / Windows + WSL2。Windows 原生跑不起来,目前不打算适配。

<details>
<summary>为什么 Windows 原生不支持</summary>

不是没适配好,是几处核心机制本身就依赖 POSIX:

| 位置 | Windows 上的问题 |
|---|---|
| daemon 收 SIGINT / SIGTERM | 用的 `loop.add_signal_handler`,Windows 事件循环没有这个 API |
| `aemeath stop` | 靠进程组信号收尾,Windows 没有进程组信号这套东西 |
| `bash` 工具 | 整个工具是按 POSIX shell 写的,落到 `cmd.exe` 上语义全变 |

硬撑着跑起来只会得到一个处处是坑的版本,所以选择明确不支持。Windows 上装个 WSL2 再照下面走:

```powershell
wsl --install          # 管理员 PowerShell,装完重启,之后所有命令都在 WSL 终端里敲
```
</details>

### 一键安装启动

```bash
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install aemeathcode && aemeath
```

检测 uv,没有就装,然后装 AemeathCode 并启动。

- 前置只有 uv 一件,Python 无需下载。已经有 pipx 也行:`pipx install aemeathcode`
- 首次启动弹配置向导,问 API Key / Base URL / 模型名。任何 Anthropic Messages API 兼容的端点都行(官方、DeepSeek、自建网关)
- 命令名 `aemeath`,包名 `aemeathcode` —— 升级卸载用包名:`uv tool upgrade aemeathcode` / `uv tool uninstall aemeathcode`
- 退出界面后 daemon 仍在后台常驻(下次秒进),`aemeath stop` 关掉

---

## 它怎么工作

### ReAct 循环

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/screenshot.png" width="100%" alt="AemeathCode 正在执行一个 run">

<sub>一个 run 正在跑:中间是工具调用和逐字输出的回答,左边是它的思考,右边是它给自己列的任务。</sub>

一个 run 是一段循环:对话发给模型 → 模型返回回答或 `tool_use` → 执行工具 → `tool_result` 写回对话 → 再次发给模型,直到不再返回 `tool_use`。

每个 `tool_use` 必须在下一轮有对应的 `tool_result`,数量与顺序都要对上,否则该轮对话被 API 拒绝。执行失败、权限拒绝、参数缺失同样返回 `tool_result`,内容为错误说明。

内置八类工具:读文件、写文件、跑 shell、列目录、任务增删查改、长期笔记、加载 skill、派子 agent。

### 动手前它会问你

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/approval.png" width="100%" alt="权限审批:写文件前弹出确认,并显示完整的待写内容">

写文件和执行命令在进入工具之前被拦截,daemon 通过同一条连接反向请求前端授权,方向与常规请求相反。授权可选「这次」或「永远」,后者会被记住。

- 审批面板展示完整的待写内容与完整命令,不截断
- 被拒绝的调用在 Content 留一行记录

### 它记得住东西

记忆分三层作用域:

| 范围 | 存什么 | 活多久 |
|---|---|---|
| 一个 run 内 | 这一轮的思考、工具调用和结果 | run 结束 |
| 一个 session 内 | 多轮对话的完整历史 | 落盘,可以 `/resume` 回来接着聊 |
| 跨 session | agent 自己用 `note_save` 写下的长期笔记、手写的项目记忆 `AEMEATH.md` | 一直在 |

消息按 run 增量存储,索引负责拼接成完整历史,恢复会话时按索引重建,不读取单一大文件。

### 上下文满了会自己压

历史逼近 token 预算时自动压缩:较早的轮次经一次独立的辅助 LLM 调用概括为摘要,最近若干轮逐字保留。压缩只作用于内存中的工作副本,磁盘上的原始记录不变,resume 得到的仍是完整历史。

### 能力边界可以往外扩

- 子 agent —— 子任务在隔离上下文中执行,只回传结果,中间过程不进入主对话;可指定角色(profiles)
- Skills —— 按需加载的操作手册,常驻的只有简介,调用 `use_skill` 时才载入正文
- MCP —— 作为客户端连接外部 server,其工具注册进同一张 ToolRegistry,在模型侧与内置工具无区别

自定义 skill、项目记忆、MCP 配置怎么写,见 [`examples/`](https://github.com/Nijikasuki/AemeathCode/tree/main/examples)。

---

## S0 → S7:它是怎么长出来的 

八个阶段推出来的,每个阶段解决一个明确的工程问题:

| 阶段 | 解决的工程问题 | 关键机制 |
|---|---|---|
| S0 | 两个进程怎么可靠通信 | 守护进程、TCP 粘包与分帧、NDJSON、JSON-RPC 2.0、asyncio 并发、优雅关闭 |
| S1 | 怎么让它自己用工具干活 | ReAct 循环、工具注册表、领域类型 / 防腐层、发布订阅事件、依赖注入 |
| S2 | 一根连接怎么同时跑请求和事件流 | 多路复用、Future 请求/响应配对、后台作业、pub/sub-over-network、状态与逻辑分离 |
| S3 | 从只读观察者到会写会跑会规划 | 异步子进程、路径安全、任务系统、Trace 可观测性、装饰器 / 包装器模式 |
| S4 | 怎么跨轮次 / 跨会话记住东西 | 记忆三层作用域、增量存储 + 索引、指针模型、tool_use/tool_result 配对铁律、进程组信号 |
| S5 | 危险操作怎么在动手前拦下来 | 反向 RPC(daemon 问客户端)、三态 policy、记住已批、fail-closed、多态替换条件分支 |
| S6 | 上下文满了怎么办 | token 预算判定、自动压缩、辅助 LLM 通道、工作副本与持久副本分家 |
| S7 | 怎么扩展能力边界 | 子 agent(隔离上下文)、角色 profiles、按需加载的 skills、MCP 客户端(stdio JSON-RPC 握手) |

对应 git tag `stage-0` … `stage-7`,可按顺序 checkout 阅读。

---

## 架构

### 两个进程,一条连接

界面和大脑是两个独立进程,中间只有一条 TCP 连接,上面同时跑三种流量。

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/diagrams/arch-link.zh.svg" width="100%" alt="两个进程,一条 TCP 连接:前端 ↔ 连接 ↔ daemon ↔ 外部 MCP server">

三种流量:

| 流量 | 方向 | 什么时候用 |
|---|---|---|
| 请求 / 响应 | 前端 → daemon → 前端 | 发起一个 run、列会话、查 token 用量 |
| 事件流 | daemon → 前端(单向推) | 模型逐字吐、工具开始 / 结束、触发压缩 |
| 反向审批 | daemon → 前端 → daemon | 要写文件、要跑命令,停下来等你点同意 |

反向审批的方向与前两种相反,daemon 是发起方。三者共用同一条连接、同一套信封格式、同一个读循环,靠信封类型区分。

### 一个 run 在 daemon 里走过哪里

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/diagrams/arch-run.zh.svg" width="100%" alt="一个 run 在 daemon 里的路径:Runner → AgentLoop,循环调用 LLMProvider 与 ToolRegistry">

图上两条回边就是循环:`tool_use` 从模型回到 loop,`tool_result` 从工具回到 loop。走向由 `stop_reason` 决定:`tool_use` 进入下一轮,`end_turn` 正常结束;`max_tokens`、`refusal`、未知值和 `max_steps` 耗尽都中止并记为失败。

源码在 `src/aemeathcode/`:

| 层 | 位置 | 职责 |
|---|---|---|
| 协议 | `bus/`、`transport/` | 信封分帧、多路复用、事件广播、反向审批管道 |
| 编排 | `core/runner.py`、`core/context.py` | 后台 run 调度、per-run 执行上下文 |
| Agent | `agent/loop.py`、`agent/tools/`、`agent/llm/` | ReAct 循环、工具注册表、LLM 防腐层 |
| 能力 | `core/permissions/`、`core/compact/`、`core/session/`、`core/memory/`、`core/trace/` | 权限、压缩、会话/记忆、可观测性 |
| 扩展 | `core/subagent`(工具内)、`core/agents/`、`core/skills/`、`core/mcp/` | 子 agent、角色、技能、MCP 客户端 |
| 前端 | `cli/`、`tui/` | 命令行 / Textual TUI |

---

## 参考

<details>
<summary><b>CLI 命令速查</b></summary>

`run` / `chat` / `watch` / `tui` 在连接前都会自动确保 daemon 在跑(没有就后台拉起),不用手动开 `core`。

| 命令 | 作用 |
|---|---|
| `aemeath` | 进入 TUI 工作台(等价于 `aemeath tui`) |
| `aemeath stop` | 关闭后台常驻的 daemon |
| `aemeath init` | 重跑配置向导,写全局配置(daemon 在跑会自动重启使其生效) |
| `aemeath init --local` | 同上,但只写当前项目的 `.aemeath/.env` |
| `aemeath mcp add <name> <命令...>` | 注册一个 MCP server(下次启动 daemon 时连上) |
| `aemeath run "<目标>"` | 单轮模式:建一个 single-turn 会话跑一发就退 |
| `aemeath chat` | 多轮模式:REPL,复用同一会话连续对话 |
| `aemeath watch` | 观察者:旁观所有正在跑的 run 的事件流 |
| `aemeath trace` | 打印最近一次运行的时间线(LLM / 工具耗时汇总) |
| `aemeath ping` | 探活:测 daemon 是否在线(不会自动拉起) |
| `aemeath core` | 手动在前台启动 daemon(想看它的日志时用;平时不用) |

TUI 里的快捷键:`^↑`/`^↓` 选会话 · `^u`/`^d` 滚 content · `^j`/`^k` 滚 thinking · `^y` 复制最后一条回答 · `^r` 复制整个 content · `^q` 退出。斜杠命令:`/resume` `/clear` `/usage` `/mcp` `/about` `/help`。

</details>

<details>
<summary><b>配置:改模型、改 Key、按项目覆盖</b></summary>

首次运行的向导已写好全局配置,`aemeath init` 可随时重跑。

配置按三级读取,上面的覆盖下面的:

| 优先级 | 位置 | 用途 |
|---|---|---|
| 1(最高) | 真正的 shell 环境变量 | 临时覆盖,如 `AEMEATH_PORT=8888 aemeath` |
| 2 | 当前目录的 `.aemeath/.env` | 这个项目专用(换模型 / 换 key) |
| 3(兜底) | `~/.config/aemeath/.env` | 全局:配一次,到处能用 |

想只给某个项目换模型或 key,三种方式随便挑:

```bash
aemeath init --local            # ① 向导写 .aemeath/.env(不带 --local 是写全局)
cp .env.example .aemeath/.env   # ② 从模板抄一份改(全部可用变量都在模板里)
                                # ③ 或者手写 .aemeath/.env,只放要覆盖的那几行
```

> 项目级配置读 `.aemeath/.env`,不是项目根目录的 `.env`。agent 有 `bash` 工具、子进程继承环境变量,只读自己的文件才不会把你的 `DATABASE_URL` 之类卷进去。`.aemeath/` 自带一张自我忽略的 `.gitignore`。

</details>

<details>
<summary><b>看源码 / 参与开发</b></summary>

```bash
git clone https://github.com/Nijikasuki/AemeathCode.git
cd AemeathCode
uv sync
uv run aemeath        # 之后所有命令前加 uv run
uv run pytest -q      # 114 passed
```

测试覆盖 framing / registry / policy / invocation / broadcaster / EventBus / skills / profiles / context / ReAct loop / budget / MCPTool / task / note / session,外加一条 MCP 端到端集成测试。

</details>

---

## 安全声明

AemeathCode 会真实执行 shell 命令、读写本地文件。内置的权限审批不能替代下面三条:

- 在隔离环境(容器 / 沙箱 / 专用目录)里运行,不要指向重要数据
- 审批时看清命令再批,`allow_always` 会被记住
- API Key 放 `.aemeath/.env` 或 `~/.config/aemeath/.env`,不要提交

本项目用于学习与研究,使用者对其行为负责。

## License

[MIT](https://github.com/Nijikasuki/AemeathCode/blob/main/LICENSE) © 2026 Nijikasuki

实现思路参考了 KamaClaude 的分阶段设计。欢迎开 issue 交流实现细节。

<div align="center">
<br>
<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/footer.gif" width="200" alt="AemeathCode">
<br><br>
</div>
