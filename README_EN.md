<div align="center">

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/mascot.gif" width="120" alt="AemeathCode mascot">

# AemeathCode

**A coding agent built from scratch —— a working terminal AI agent, and a visible journey through systems engineering.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/Nijikasuki/AemeathCode/blob/main/LICENSE)
[![Built with asyncio](https://img.shields.io/badge/built%20with-asyncio-blue)](https://docs.python.org/3/library/asyncio.html)
[![TUI: Textual](https://img.shields.io/badge/TUI-Textual-5A5AFF)](https://textual.textualize.io/)
[![MCP](https://img.shields.io/badge/MCP-client-orange)](https://modelcontextprotocol.io/)
[![CI](https://github.com/Nijikasuki/AemeathCode/actions/workflows/ci.yml/badge.svg)](https://github.com/Nijikasuki/AemeathCode/actions/workflows/ci.yml)

[简体中文](https://github.com/Nijikasuki/AemeathCode/blob/main/README.md) · **English**

</div>

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/splash.png" width="100%" alt="The AemeathCode TUI right after launch">

<sub>Left: Status / Sessions / Thinking · Middle: Content and the prompt · Right: Tasks / Changes / MCP / Skills.</sub>

---

## What it is

Give it a goal and it plans the steps, reads and writes files, runs commands, observes results, and keeps looping until the job is done —— all visible live in your terminal.

It is two processes: a frontend and a resident background daemon, joined by a multiplexed protocol implemented here from scratch. The ReAct loop, tool registry, session memory, permission approval, context compaction, sub-agents and the MCP client are all pure Python + asyncio —— no agent framework involved.

This is a learning and showcase project. It really executes shell commands and really writes files —— run it in a directory you trust (see [Security](#security)).

---

## Install and run

Supported on Linux / macOS / Windows + WSL2. Native Windows does not work, and there are no plans to port it.

<details>
<summary>Why native Windows isn't supported</summary>

It isn't a porting gap — several core mechanisms are POSIX by design:

| Where | The problem on Windows |
|---|---|
| Daemon receiving SIGINT / SIGTERM | Uses `loop.add_signal_handler`, absent from the Windows event loop |
| `aemeath stop` | Shuts down via process-group signals, which Windows has no equivalent of |
| The `bash` tool | Written against a POSIX shell throughout; on `cmd.exe` the semantics change entirely |

Forcing it to start would only produce a version full of holes, so it's explicitly unsupported. On Windows, install WSL2 and follow the steps below inside it:

```powershell
wsl --install          # admin PowerShell, then reboot; run everything in the WSL terminal afterwards
```
</details>

### One-shot install and run

```bash
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install aemeathcode && aemeath
```

Checks for uv, installs it if missing, then installs AemeathCode and launches it. After that, just run `aemeath`.

- uv is the only prerequisite; you don't have to install Python yourself. Already have pipx? `pipx install aemeathcode`
- First launch opens a setup wizard: API key / base URL / model name. Any Anthropic Messages API–compatible endpoint works (official, DeepSeek, your own gateway)
- Command is `aemeath`, package is `aemeathcode` — upgrade and uninstall use the package name: `uv tool upgrade aemeathcode` / `uv tool uninstall aemeathcode`
- Quitting the UI leaves the daemon resident (next launch is instant); `aemeath stop` shuts it down

### Harness overview

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/about.png" width="100%" alt="/about: version, model, session id and context usage">

<sub>`/about` —— version, model, session id, context usage.</sub>

---

## How it works

### The ReAct loop

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/screenshot.png" width="100%" alt="AemeathCode executing a run">

<sub>A run in progress: tool calls and the streaming answer in the middle, its thinking on the left, the tasks it wrote for itself on the right.</sub>

A run is a loop: the conversation goes to the model → the model returns an answer or a `tool_use` → the tool runs → the `tool_result` is written back → the conversation goes out again, until no `tool_use` comes back.

Every `tool_use` must be matched by a `tool_result` on the next turn, in the same count and order, or the API rejects that turn. Execution failures, permission denials and missing arguments all return a `tool_result` too, carrying the error as its content.

Eight built-in tool families: read file, write file, run shell, list directory, task CRUD, long-term notes, load a skill, spawn a sub-agent.

### It asks before it acts

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/approval.png" width="100%" alt="Permission approval: a confirmation before writing a file, showing the full content to be written">

Writing files and running commands are intercepted before the tool runs; the daemon requests authorization from the frontend over the same connection, in the reverse direction of a normal request. Approval can be once or always; always is remembered.

- The approval panel shows the full content to be written and the full command, untruncated
- Denied calls leave a line in Content

### It remembers

Memory has three scopes:

| Scope | What it holds | How long it lives |
|---|---|---|
| Within a run | This round's thinking, tool calls and results | Until the run ends |
| Within a session | Full multi-turn conversation history | On disk; `/resume` to pick it back up |
| Across sessions | Long-term notes the agent writes via `note_save`, plus the project memory `AEMEATH.md` | Permanent |

Messages are stored incrementally per run; an index stitches them into full history, so resuming rebuilds from the index rather than reading one ever-growing file.

### It compacts itself when context fills up

As history approaches the token budget, compaction runs automatically: older turns are summarized by a separate auxiliary LLM call, the most recent turns are kept verbatim. Compaction only touches the in-memory working copy — the record on disk is unchanged, so a resumed session still gets the full history.

### The capability boundary is extensible

- Sub-agents —— a sub-task runs in an isolated context and only its result comes back; intermediate steps never enter the main conversation. Roles are selectable (profiles)
- Skills —— on-demand playbooks; only the summary is resident, the body loads when `use_skill` is called
- MCP —— acts as a client to external servers and registers their tools into the same ToolRegistry, indistinguishable from built-ins on the model's side

See [`examples/`](https://github.com/Nijikasuki/AemeathCode/tree/main/examples) for how to write custom skills, project memory, and MCP config.

---

## S0 → S7: how it grew

Eight stages, each solving one concrete engineering problem:

| Stage | Engineering problem | Key mechanisms |
|---|---|---|
| S0 | How can two processes communicate reliably | Daemon, TCP framing, NDJSON, JSON-RPC 2.0, asyncio concurrency, graceful shutdown |
| S1 | How to make it use tools on its own | ReAct loop, tool registry, domain types / anti-corruption layer, pub/sub events, dependency injection |
| S2 | How one link carries both requests and an event stream | Multiplexing, Future-based request/response pairing, background jobs, pub/sub-over-network, state/logic separation |
| S3 | From read-only observer to writing, running, planning | Async subprocesses, path safety, task system, trace observability, decorator/wrapper pattern |
| S4 | How to remember across turns and sessions | Three memory scopes, incremental storage + index, pointer model, the tool_use/tool_result pairing rule, process-group signals |
| S5 | How to intercept dangerous operations before they happen | Reverse RPC (daemon asks the client), tri-state policy, remembered approvals, fail-closed, polymorphism over conditionals |
| S6 | What to do when context fills up | Token budget checks, auto-compaction, auxiliary LLM channel, working copy vs. persistent copy |
| S7 | How to extend the capability boundary | Sub-agents (isolated context), agent profiles, on-demand skills, MCP client (stdio JSON-RPC handshake) |

Matching git tags: `stage-0` … `stage-7`, checkout in order to read along.

---

## Architecture

### Two processes, one connection

The interface and the brain are separate processes, joined by exactly one TCP connection carrying three kinds of traffic.

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/diagrams/arch-link.en.svg" width="100%" alt="Two processes, one TCP connection: frontend ↔ link ↔ daemon ↔ external MCP server">

The three kinds of traffic:

| Traffic | Direction | When |
|---|---|---|
| Request / response | frontend → daemon → frontend | Start a run, list sessions, query token usage |
| Event stream | daemon → frontend (one-way push) | Model streaming tokens, tool start / finish, compaction fired |
| Reverse approval | daemon → frontend → daemon | About to write a file or run a command — stops and waits for your yes |

Reverse approval runs opposite to the other two: the daemon is the asker. All three share one connection, one envelope format and one read loop, distinguished by envelope type.

### Where a run goes inside the daemon

<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/diagrams/arch-run.en.svg" width="100%" alt="A run inside the daemon: Runner → AgentLoop, looping through LLMProvider and ToolRegistry">

The two back-edges in the diagram are the loop: `tool_use` from the model, `tool_result` from the tools. `stop_reason` decides what comes next: `tool_use` runs another turn, `end_turn` finishes normally; `max_tokens`, `refusal`, an unknown value and an exhausted `max_steps` all abort as failures.

Source lives in `src/aemeathcode/`:

| Layer | Location | Responsibility |
|---|---|---|
| Protocol | `bus/`, `transport/` | Envelope framing, multiplexing, event broadcast, reverse-approval pipe |
| Orchestration | `core/runner.py`, `core/context.py` | Background run scheduling, per-run execution context |
| Agent | `agent/loop.py`, `agent/tools/`, `agent/llm/` | ReAct loop, tool registry, LLM anti-corruption layer |
| Capabilities | `core/permissions/`, `core/compact/`, `core/session/`, `core/memory/`, `core/trace/` | Permissions, compaction, sessions/memory, observability |
| Extensions | `core/subagent` (in-tool), `core/agents/`, `core/skills/`, `core/mcp/` | Sub-agents, roles, skills, MCP client |
| Frontend | `cli/`, `tui/` | Command line / Textual TUI |

---

## Reference

<details>
<summary><b>CLI commands</b></summary>

`run` / `chat` / `watch` / `tui` all ensure the daemon is running before connecting (spawning it if needed) —— no need to start `core` by hand.

| Command | What it does |
|---|---|
| `aemeath` | Enter the TUI workbench (same as `aemeath tui`) |
| `aemeath stop` | Shut down the resident background daemon |
| `aemeath init` | Re-run the setup wizard, writing global config (restarts a running daemon so it takes effect) |
| `aemeath init --local` | Same, but writes this project's `.aemeath/.env` |
| `aemeath mcp add <name> <command...>` | Register an MCP server (connected on the next daemon start) |
| `aemeath run "<goal>"` | One-shot: create a single-turn session, run once, exit |
| `aemeath chat` | Multi-turn: a REPL reusing one session |
| `aemeath watch` | Observer: watch the event stream of every running run |
| `aemeath trace` | Print the timeline of the latest run (LLM / tool timing summary) |
| `aemeath ping` | Health check: is the daemon up (does not auto-spawn) |
| `aemeath core` | Start the daemon in the foreground (to read its logs; usually unneeded) |

Keys inside the TUI: `^↑`/`^↓` switch session · `^u`/`^d` scroll content · `^j`/`^k` scroll thinking · `^y` copy the last answer · `^r` copy all content · `^q` quit. Slash commands: `/resume` `/clear` `/usage` `/mcp` `/about` `/help`.

</details>

<details>
<summary><b>Configuration: change model, change key, override per project</b></summary>

The first-run wizard already wrote your global config; `aemeath init` re-runs it any time.

Config is read from three levels, higher overrides lower:

| Priority | Location | Purpose |
|---|---|---|
| 1 (highest) | Real shell environment variables | One-off override, e.g. `AEMEATH_PORT=8888 aemeath` |
| 2 | `.aemeath/.env` in the current directory | Per-project (different model / key) |
| 3 (fallback) | `~/.config/aemeath/.env` | Global: configure once, works anywhere |

To change the model or key for one project only, take your pick:

```bash
aemeath init --local            # 1. wizard writes .aemeath/.env (without --local it writes global)
cp .env.example .aemeath/.env   # 2. copy the template and edit (every variable is listed there)
                                # 3. or hand-write .aemeath/.env with only the lines you override
```

> Project config lives in `.aemeath/.env`, not your project's own `.env`. The agent has a `bash` tool whose subprocesses inherit the environment; reading only our own file keeps your `DATABASE_URL` and friends out of it. `.aemeath/` ships with a self-ignoring `.gitignore`.

</details>

<details>
<summary><b>Reading the source / developing</b></summary>

```bash
git clone https://github.com/Nijikasuki/AemeathCode.git
cd AemeathCode
uv sync
uv run aemeath        # prefix commands with uv run
uv run pytest -q      # 114 passed
```

Tests cover framing / registry / policy / invocation / broadcaster / EventBus / skills / profiles / context / ReAct loop / budget / MCPTool / task / note / session, plus one MCP end-to-end integration test.

</details>

---

## Security

AemeathCode really executes shell commands and reads/writes local files. Built-in permission approval does not replace these three:

- Run it in an isolated environment (container / sandbox / dedicated directory), never pointed at data that matters
- Read the command before approving; `allow_always` is remembered
- Keep your API key in `.aemeath/.env` or `~/.config/aemeath/.env`, never commit it

This project is for learning and research; users are responsible for its behavior.

## License

[MIT](https://github.com/Nijikasuki/AemeathCode/blob/main/LICENSE) © 2026 Nijikasuki

The staged design was inspired by KamaClaude. Issues discussing implementation details are welcome.

<div align="center">
<br>
<img src="https://raw.githubusercontent.com/Nijikasuki/AemeathCode/main/assets/footer.gif" width="200" alt="AemeathCode">
<br><br>
</div>
