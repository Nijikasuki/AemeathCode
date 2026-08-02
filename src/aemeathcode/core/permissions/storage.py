import json
from pathlib import Path


class PermissionStore:
    """记住用户 allow_always 批过的权限。

    作用域:项目级(跟 note 一样落项目内,base_dir 注入 → 该项目所有 session 共享、
    跨 session 不丢,且测试可隔离)。

    数据形状:一张扁平表 {key: decision}。key 由 manager 按工具算好再传进来
    (如 "bash:rm" / "write_file:/home/x/proj"),storage 只负责存/读,不懂怎么算 key。
    只有 allow_always 会落盘,所以 value 目前恒为 "allow"。
    """

    def __init__(self, base_dir: Path):
        self._path = base_dir / "permissions.json"

    def load(self) -> dict[str, str]:
        # 文件不存在(首次跑) / 内容损坏 → 都退回空表,别让一个坏文件掀翻审批流
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        # json 合法但不是 dict(如被写成 [] / 数字)也退空表,别让下游当 dict 用时炸
        return data if isinstance(data, dict) else {}

    def remember(self, key: str, decision: str = "allow") -> None:
        # 读-改-写:权限落盘是人工节奏的低频操作,不担心并发
        data = self.load()
        data[key] = decision
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
