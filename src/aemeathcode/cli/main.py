import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from aemeathcode.transport.socket_client import SocketClient, IpcError
from aemeathcode.core.app import main as app_main
from aemeathcode.cli.stream_renderer import StreamRenderer
from aemeathcode.cli.bootstrap import ensure_daemon, _probe
from aemeathcode.core.config import get_address


async def _ping():
    client = SocketClient(*get_address())
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())  # 分拣室后台跑
    pong = await client.send_command("ping", {})
    print(pong)
    loop_task.cancel()  # 收工：停分拣室
    await client.close()

async def _run(goal:str):
    await ensure_daemon()       # 没 daemon 就自动拉起,连接前先确保它在
    client = SocketClient(*get_address())
    await client.connect()

    done = asyncio.Event()
    renderer = StreamRenderer()

    async def on_event(event):  # 事件处理器
        renderer.feed(event)
        if event.get("type") == "run.completed" and event["run_id"]==ack["run_id"]:
            done.set()

    client.on_event(on_event)
    client.on_ask(_prompt_ask)                                # 反向审批:daemon 问,命令行答
    loop_task = asyncio.create_task(client.run_event_loop())

    # run 也要 session:一次性执行 = 建一个 single_turn 会话,只跑这一发
    session = await client.send_command("session.create", {"mode": "single_turn"})
    session_id = session["session_id"]

    ack = await client.send_command("run", {"goal": goal, "session_id": session_id})
    print(f"🚀 已启动 (run_id={ack['run_id']})")

    await done.wait()  # 盯着旗，等 run.completed

    loop_task.cancel()  # 收工：停分拣室
    await client.close()


async def _read_line(prompt:str) -> str | None:
    """异步读一行:线程池里读原始字节,自己按 UTF-8 解码;EOF 返回 None。

    读 bytes 自己 decode(不走 input()):input() 依赖 locale 解码,多字节中文会被解成
    surrogate 代理字符,后续 JSON 序列化直接炸。

    Ctrl+C 时这个工作线程会卡在 readline 上无法干净收尾 —— 由 main() 用 os._exit 硬退兜底。"""
    loop = asyncio.get_running_loop()
    print(prompt, end="", flush=True)
    raw = await loop.run_in_executor(None, sys.stdin.buffer.readline)
    if not raw:  # 空字节 = EOF(Ctrl+D)
        return None
    return raw.decode("utf-8", errors="replace")


async def _prompt_ask(ask: dict) -> str:
    """CLI 侧的审批应答器:daemon 反向问权限时,打印请求 + 读 stdin 让用户拍板。

    安全用 _read_line(不怕和主输入循环抢 stdin):审批只在 run 进行中发生,那时
    _run/_chat 都停在 await done.wait(),没在读 stdin,两者天然错开。
    EOF / 乱输入 → deny(fail-closed,跟 TUI 的 Esc=deny 一致)。"""
    tool = ask.get("tool_name", "")
    detail = ask.get("detail", "")
    print(f"\n⚠️  权限请求 · {tool}: {detail}")
    line = await _read_line("[1] 允许一次  [2] 总是允许  [3] 拒绝 > ")
    if line is None:
        return "deny"
    return {"1": "allow_once", "2": "allow_always", "3": "deny"}.get(line.strip(), "deny")


def _print_sessions(sessions):
    if not sessions:
        print("(还没有历史会话)")
        return
    print("历史会话(最近在前):")
    for s in sessions:
        updated = (s.get("updated_at") or "")[:19]
        title = s.get("title") or "(无标题)"
        print(f"  {s.get('id')}  {updated}  {title}")   # 完整 id,方便 /resume 复制


def _extract_text(content) -> str:
    """从一条 message 的 content 抽可读文本:str 直接用;list 取 text 块。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _replay_history(history):
    if not history:
        print("(这个会话还没有历史)")
        return
    print("──── 历史对话 ────")
    for msg in history:
        text = _extract_text(msg.get("content"))
        if not text.strip():
            continue   # 跳过纯 tool_use / tool_result 这类没文本的消息
        prefix = "❯" if msg.get("role") == "user" else "🤖"
        print(f"{prefix} {text}")
    print("──────────────────")


async def _chat():
    await ensure_daemon()       # 没 daemon 就自动拉起,连接前先确保它在
    client = SocketClient(*get_address())
    await client.connect()

    done = asyncio.Event()
    renderer = StreamRenderer()

    async def on_event(event):
        renderer.feed(event)
        if event.get("type") == "run.completed" and event["run_id"]==ack["run_id"]:
            done.set()

    client.on_event(on_event)
    client.on_ask(_prompt_ask)                                # 反向审批:daemon 问,命令行答
    loop_task = asyncio.create_task(client.run_event_loop())  # 读循环后台常驻

    # 多轮对话 = 一个 multi_turn 会话,全程复用同一个 session_id
    session = await client.send_command("session.create", {"mode": "multi_turn"})
    session_id = session["session_id"]
    print(f"💬 会话已开始 (session={session_id[:8]})   "
          f"/sessions · /resume <id> · /clear · /usage\n"
          f"   退出:/exit(或 Ctrl+D / Ctrl+C)\n")

    try:
        while True:
            line = await _read_line("❯ ")
            if line is None:      # EOF(Ctrl+D)
                print()
                break
            text = line.strip()
            if not text:
                continue

            # 斜杠命令:在发 run【之前】分流,命令本身不当 goal 发出去
            if text.startswith("/"):
                if text in ("/exit", "/quit"):
                    break
                elif text == "/sessions":
                    resp = await client.send_command("session.list", {})
                    _print_sessions(resp["sessions"])
                elif text == "/usage":
                    resp = await client.send_command("session.usage", {"session_id": session_id})
                    if isinstance(resp, str):
                        print(resp)
                    else:
                        print(f"📊 本会话累计 token:输入 {resp['input_tokens']} · "
                              f"输出 {resp['output_tokens']} · 缓存读 {resp['cache_read']}")
                elif text == "/clear":
                    created = await client.send_command("session.create", {"mode": "multi_turn"})
                    session_id = created["session_id"]
                    print(f"🧹 已开新会话 (session={session_id[:8]})")
                elif text.startswith("/resume"):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        print("用法:/resume <session_id>")
                        continue
                    resp = await client.send_command("session.resume", {"session_id": parts[1].strip()})
                    if isinstance(resp, str):      # handler 用字符串报错(如"会话不存在")
                        print(resp)
                        continue
                    session_id = resp["session_id"]
                    print(f"⏪ 已恢复会话 (session={session_id[:8]}  {resp.get('title') or ''})")
                    _replay_history(resp["history"])
                else:
                    print(f"未知命令:{text}  (可用:/sessions  /resume <id>  /clear  /exit)")
                continue   # 命令处理完,不往下发 run

            # 普通输入 = 一轮对话
            done.clear()          # 先清旗,免得上一轮的 set 漏到这轮
            ack = await client.send_command("run", {"goal": text, "session_id": session_id})
            await done.wait()     # 等这一轮 run.completed,再回去读下一句
    finally:
        loop_task.cancel()
        await client.close()
        print("再见 👋")

async def _watch(scope:str, topics:list[str]):
    await ensure_daemon()       # 没 daemon 就自动拉起,连接前先确保它在
    client = SocketClient(*get_address())
    await client.connect()
    renderer = StreamRenderer()

    async def on_event(event):
        renderer.feed(event)

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())
    ack = await client.send_command("watch", {"scope": scope, "topics": topics})
    print(f"观察模式已启动,scope={ack["subscribed"]}")
    await loop_task


async def _stop():
    """请求 daemon 优雅关闭:探活→没有就直说→有就连上发 shutdown。

    daemon 关闭时连接会断,send_command 的响应可能收不到(读循环里挂起的 future 被
    置成 ConnectionError)—— 那是预期的,吞掉当成功。"""
    if not await _probe():
        print("daemon 未在运行")
        return
    client = SocketClient(*get_address())
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    ok = True
    try:
        await client.send_command("shutdown", {})   # 正常返回 "shutting down" = 成功
    except ConnectionError:
        pass          # 连接随 daemon 关闭而断,收不到回执 —— 也是成功
    except IpcError as e:
        ok = False    # 收到错误响应(如老 daemon 没有 shutdown handler)= daemon 拒绝了
        print(f"关闭失败:{e}")
    loop_task.cancel()
    try:
        await client.close()
    except Exception:
        pass
    if ok:
        print("🛑 已请求 daemon 关闭")


def cmd_ping(args):
    asyncio.run(_ping())

def cmd_core(args):
    asyncio.run(app_main())

def cmd_run(args):
    asyncio.run(_run(args.goal))

def cmd_chat(args):
    asyncio.run(_chat())

def cmd_watch(args):
    asyncio.run(_watch(args.scope, args.topics))

def cmd_tui(args):
    # 进 textual 前先确保 daemon 在(textual 会自建事件循环,这里先跑个短的把 daemon 拉起)
    asyncio.run(ensure_daemon())
    # 延迟导入:只有真进 TUI 才加载 textual,别的子命令不受影响
    from aemeathcode.tui.app import run as run_tui
    run_tui()

def cmd_stop(args):
    asyncio.run(_stop())

def cmd_trace(args):
    # trace 不连 daemon,纯读本地文件,所以是同步的,不用 asyncio.run
    from aemeathcode.core.trace.record import TraceRecord
    from aemeathcode.core.config import get_data_dir

    run_dir = get_data_dir() / "run"  # 与 daemon 写入路径统一到 config,不再各写各的
    files = sorted(run_dir.glob("traces_*.ndjson"))  # 文件名带时间戳,字典序=时间序
    if not files:
        print("还没有 trace 文件(先跑一个 aemeath run)")
        return
    path = files[-1]  # 最新那个

    records = [
        TraceRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        print(f"{path.name} 是空的")
        return

    print(f"Trace: run {records[0].run_id[:8]}  ({path.name})\n")

    t0 = datetime.fromisoformat(records[0].ts)
    llm_total = tool_total = 0.0
    llm_n = tool_n = 0
    for r in records:
        rel_ms = (datetime.fromisoformat(r.ts) - t0).total_seconds() * 1000
        mark = "✗" if r.status == "error" else " "
        print(f"  {mark} +{rel_ms:>7.0f}ms  {r.category:<4}  {r.name:<24}  {r.duration_ms:>9.1f}ms  {r.status}")
        if r.category == "llm":
            llm_total += r.duration_ms
            llm_n += 1
        else:
            tool_total += r.duration_ms
            tool_n += 1

    print()
    print("  ── 汇总 ──")
    print(f"  LLM   {llm_n} 次   {llm_total:>9.1f}ms")
    print(f"  工具  {tool_n} 次   {tool_total:>9.1f}ms")
    print(f"  总计          {llm_total + tool_total:>9.1f}ms")

def cmd_mcp_add(args):
    from aemeathcode.core.mcp.config import add_server
    if not args.command:
        print("用法:aemeath mcp add <name> <命令...>"
              "(如 aemeath mcp add github npx -y @modelcontextprotocol/server-github)")
        return
    add_server(args.name, args.command)
    print(f"已添加 MCP server '{args.name}':{' '.join(args.command)}")
    print("重启 aemeath core 生效")


def main():
    parser = argparse.ArgumentParser(prog='aemeath')
    # 不传子命令时默认进 TUI(类似 claude code:敲 aemeath 直接进界面)
    parser.set_defaults(func=cmd_tui)
    subparsers = parser.add_subparsers(dest="command")

    p_core = subparsers.add_parser('core')
    p_core.set_defaults(func=cmd_core)

    p_run = subparsers.add_parser('run')     # 一次性:建 single_turn 会话跑一发
    p_run.add_argument("goal")
    p_run.set_defaults(func=cmd_run)

    p_chat = subparsers.add_parser('chat')   # 多轮:建 multi_turn 会话,REPL 复用
    p_chat.set_defaults(func=cmd_chat)

    p_ping = subparsers.add_parser("ping")
    p_ping.set_defaults(func=cmd_ping)

    p_stop = subparsers.add_parser("stop")   # 手动关闭后台 daemon(混合生命周期:退出不自动关)
    p_stop.set_defaults(func=cmd_stop)

    p_watch = subparsers.add_parser('watch')
    p_watch.add_argument("--scope", default="global")
    p_watch.add_argument("--topics", default=["*"])
    p_watch.set_defaults(func=cmd_watch)

    p_tui = subparsers.add_parser('tui')     # 显式写法,和裸 aemeath 等价
    p_tui.set_defaults(func=cmd_tui)

    p_trace = subparsers.add_parser('trace')  # 读最新 trace 文件,打印时间线
    p_trace.set_defaults(func=cmd_trace)

    p_mcp = subparsers.add_parser('mcp')       # 管理 MCP server
    p_mcp.set_defaults(func=lambda a: print("用法:aemeath mcp add <name> <命令...>"))
    mcp_sub = p_mcp.add_subparsers(dest="mcp_command")
    p_mcp_add = mcp_sub.add_parser('add')      # aemeath mcp add <name> <命令...>
    p_mcp_add.add_argument("name")
    p_mcp_add.add_argument("command", nargs=argparse.REMAINDER)  # 剩下的全当命令(含 -y 这种 flag)
    p_mcp_add.set_defaults(func=cmd_mcp_add)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        # Ctrl+C:读 stdin 的工作线程还卡在 readline 上,正常关闭流程会被它绊住
        # (join 卡死 / 抢 stdin 缓冲锁 fatal)。os._exit 硬退,跳过 atexit 与 IO finalize,
        # 那个卡住的线程随进程一起被系统回收。此时 _chat 的 finally 已跑完(连接已关)。
        sys.stdout.flush()
        os._exit(0)

if __name__ == "__main__":
    main()