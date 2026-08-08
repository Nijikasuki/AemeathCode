"""单命令启动:客户端负责把 daemon 弄起来。

心智:前端(TUI/CLI)启动时先探活 daemon —— 连得上就复用,连不上就自己在后台
拉起一个脱离终端的 daemon 进程,等它 ready 再让上层去连。用户只敲一个 `aemeath`,
双进程架构(常驻、可多 client、隔离)的好处一个不丢。是 docker / gh / tmux 的做法。
"""
import asyncio
import subprocess
import sys

from aemeathcode.core.config import get_address, get_data_dir
from aemeathcode.transport.socket_client import SocketClient


async def _probe(timeout: float = 0.5) -> bool:
    """连一下 + ping,通了返回 True。任何异常都吞掉返回 False —— 探活自己绝不能炸。

    send_command 要靠 run_event_loop 在后台读响应才能 resolve,所以探活也得临时把
    读循环跑起来;无论成败都在 finally 里收干净(cancel 读循环 + close 连接)。"""
    client = SocketClient(*get_address())
    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
    except (OSError, asyncio.TimeoutError):
        return False  # daemon 不在:connect 直接 ConnectionRefused,不会等满 timeout
    loop_task = asyncio.create_task(client.run_event_loop())
    try:
        await asyncio.wait_for(client.send_command("ping", {}), timeout=timeout)
        return True
    except Exception:
        return False  # 连上了但 ping 不通(daemon 半死):也算不可用
    finally:
        loop_task.cancel()
        try:
            await client.close()
        except Exception:
            pass


def _spawn_daemon() -> None:
    """在后台拉起一个脱离终端的 daemon,立即返回(等它 ready 是 _wait_ready 的事)。

    三个必须项,缺一个都有坑:
      · start_new_session=True → 脱离控制终端/进程组,daemon 独立于我而活
        (S4 那把'建独立进程组'的刀的反面用法:那时为一锅端杀,这里为独立存活)
      · stdout/stderr 重定向到日志文件 → 别让 daemon 日志喷进 TUI 屏幕
        ⚠️ 千万别用 PIPE:没人读,管子写满 daemon 直接卡死
      · stdin=DEVNULL → 别让它跟前端抢终端输入
    命令用 `-m aemeathcode.core.app` 而非 PATH 里的 aemeath:不依赖安装方式,最稳。"""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "core.log"
    # with 退出时 close 的是父进程这份副本;子进程已 dup 到自己的 fd,不受影响
    with open(log_path, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, "-m", "aemeathcode.core.app"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


async def _wait_ready(attempts: int = 50, interval: float = 0.1) -> bool:
    """轮询探活直到 daemon ready(最多 attempts×interval,默认约 5s)。

    不许 sleep 一个固定秒数赌它起来了:机器慢就崩、快就白等。"""
    for _ in range(attempts):
        if await _probe():
            return True
        await asyncio.sleep(interval)
    return False


async def ensure_daemon() -> None:
    """对外唯一入口:确保 daemon 在跑。探活通了直接复用;没通就拉起 + 等 ready。

    竞态无忧:万一两个前端同时拉起,daemon 的'防重复启动'(端口被占即退出,S0)
    会让后来者自己死掉、前者赢,天然兜住。"""
    if await _probe():
        return  # 复用已有 daemon,秒进
    _spawn_daemon()
    if not await _wait_ready():
        raise RuntimeError(
            f"daemon 启动失败。请查看日志:{get_data_dir() / 'core.log'}"
        )
