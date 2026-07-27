import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from aemeathcode.transport.socket_client import SocketClient
from aemeathcode.core.app import main as app_main
from aemeathcode.cli.stream_renderer import StreamRenderer


async def _ping():
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())  # 分拣室后台跑
    pong = await client.send_command("ping", {})
    print(pong)
    loop_task.cancel()  # 收工：停分拣室
    await client.close()

async def _run(goal:str):
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()

    done = asyncio.Event()
    renderer = StreamRenderer()

    async def on_event(event):  # 事件处理器
        renderer.feed(event)
        if event.get("type") == "run.completed":
            done.set()

    client.on_event(on_event)
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
    """异步读一行:线程池里读【原始字节】,自己按 UTF-8 解码;EOF 返回 None。

    不走 input():input() 用 readline 模块 + 依赖 locale 做文本解码,在工作线程里反复
    调用会把多字节中文解成 surrogate 代理字符,后续 JSON 序列化直接炸。读 bytes 自己
    decode 既绕开 readline 的线程问题,也绕开 locale 解码,最稳。"""
    loop = asyncio.get_running_loop()
    print(prompt, end="", flush=True)
    raw = await loop.run_in_executor(None, sys.stdin.buffer.readline)
    if not raw:  # 空字节 = EOF(Ctrl+D)
        return None
    return raw.decode("utf-8", errors="replace")


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
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()

    done = asyncio.Event()
    renderer = StreamRenderer()

    async def on_event(event):
        renderer.feed(event)
        if event.get("type") == "run.completed":
            done.set()

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())  # 读循环后台常驻

    # 多轮对话 = 一个 multi_turn 会话,全程复用同一个 session_id
    session = await client.send_command("session.create", {"mode": "multi_turn"})
    session_id = session["session_id"]
    print(f"💬 会话已开始 (session={session_id[:8]})   "
          f"/sessions · /resume <id> · /clear · /usage · /exit\n")

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
            await client.send_command("run", {"goal": text, "session_id": session_id})
            await done.wait()     # 等这一轮 run.completed,再回去读下一句
    finally:
        loop_task.cancel()
        await client.close()
        print("再见 👋")

async def _watch(scope:str, topics:list[str]):
    client = SocketClient("127.0.0.1", 9999)
    await client.connect()
    renderer = StreamRenderer()

    async def on_event(event):
        renderer.feed(event)

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())
    ack = await client.send_command("watch", {"scope": scope, "topics": topics})
    print(f"观察模式已启动,scope={ack["subscribed"]}")
    await loop_task

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
    # 延迟导入:只有真进 TUI 才加载 textual,别的子命令不受影响
    from aemeathcode.tui.app import run as run_tui
    run_tui()

def cmd_trace(args):
    # trace 不连 daemon,纯读本地文件,所以是同步的,不用 asyncio.run
    from aemeathcode.core.trace.record import TraceRecord

    run_dir = Path("run")  # 约定从项目根目录运行
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

    p_watch = subparsers.add_parser('watch')
    p_watch.add_argument("--scope", default="global")
    p_watch.add_argument("--topics", default=["*"])
    p_watch.set_defaults(func=cmd_watch)

    p_tui = subparsers.add_parser('tui')     # 显式写法,和裸 aemeath 等价
    p_tui.set_defaults(func=cmd_tui)

    p_trace = subparsers.add_parser('trace')  # 读最新 trace 文件,打印时间线
    p_trace.set_defaults(func=cmd_trace)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()