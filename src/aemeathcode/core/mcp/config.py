"""MCP server 的持久配置(.aemeath/mcp.json)。

一条记录 = {"name": 名字, "command": ["拉起命令", "参数"...]}。
`aemeath mcp add` 写它;daemon 启动时 load 它、连上里面每个 server。
加了要【重启 core】生效(v1;热连接是增强)。
"""
import json
from pathlib import Path

from aemeathcode.core.config import get_data_dir


def _config_path() -> Path:
    return get_data_dir() / "mcp.json"


def load_servers() -> list[dict]:
    """读出用户配的 server 列表;文件缺失/损坏都返回空,不炸。"""
    path = _config_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def add_server(name: str, command: list[str]) -> None:
    """加一个(同名覆盖),写回 mcp.json。"""
    servers = [s for s in load_servers() if s.get("name") != name]
    servers.append({"name": name, "command": command})
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(servers, ensure_ascii=False, indent=2), encoding="utf-8")
