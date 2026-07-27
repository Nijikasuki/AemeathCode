import json
from pathlib import Path

from aemeathcode.core.session.model import Session
from aemeathcode.core.task.manager import TaskManager


class SessionStore:
    """会话的本地磁盘持久化:一 session 一文件夹(meta.json + messages.ndjson)。

    base_dir 由外部注入 —— 生产环境从 config 传,测试里指向临时目录,互不污染。
    """

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def save_meta(self, runtime):
        meta = {
            "session": runtime.session.model_dump(mode="json"),
            "tokens": {
                "total_input_tokens": runtime.total_input_tokens,
                "total_output_tokens": runtime.total_output_tokens,
                "total_cache_read": runtime.total_cache_read,
            },
            "tasks": runtime.tasks.to_dict(),
        }

        session_dir = self._base_dir / runtime.session.id
        session_dir.mkdir(parents=True, exist_ok=True)

        meta_path = session_dir / "meta.json"
        with meta_path.open("w", encoding="utf-8") as file:
            json.dump(meta, file, ensure_ascii=False, indent=2)

    def append_run(self, session_id, run_id, increment):
        run_record = {
            "run_id": run_id,
            "messages": increment,
        }
        file_path = self._base_dir / session_id / "messages.ndjson"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(run_record, ensure_ascii=False) + "\n")

    def load_session(self, session_id: str):
        session_dir = self._base_dir / session_id
        meta_path = session_dir / "meta.json"
        messages_path = session_dir / "messages.ndjson"

        if not session_dir.exists():
            raise FileNotFoundError(f"Session 不存在: {session_id}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Session 元数据不存在: {meta_path}")

        # 1. 读取 meta.json
        with meta_path.open("r", encoding="utf-8") as file:
            meta = json.load(file)

        # 2. 重建 Session 模型
        session_data = meta.get("session")
        if session_data is None:
            raise ValueError(f"meta.json 缺少 session 字段: {meta_path}")
        session = Session.model_validate(session_data)

        # 3. 重建 token 统计(带默认,兼容老存档)
        tokens = meta.get(
            "tokens",
            {"total_input_tokens": 0, "total_output_tokens": 0, "total_cache_read": 0},
        )

        # 4. 重建 tasks(借 classmethod 工厂)
        tasks = TaskManager.from_dict(meta.get("tasks", {}))

        # 5. 重建 run_messages:逐行读 ndjson,靠 run_id 把 dict 结构长回来
        run_messages: dict[str, list[dict]] = {}
        if messages_path.exists():
            with messages_path.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    run_messages[record["run_id"]] = record["messages"]

        return {
            "session": session,
            "run_messages": run_messages,
            "tasks": tasks,
            "tokens": tokens,
        }

    def list_sessions(self):
        if not self._base_dir.exists():
            return []

        sessions = []
        for session_dir in self._base_dir.iterdir():
            meta_path = session_dir / "meta.json"
            if not session_dir.is_dir() or not meta_path.exists():
                continue  # 跳过非目录 / 缺 meta 的半成品
            with meta_path.open("r", encoding="utf-8") as file:
                meta = json.load(file)
            session = meta.get("session", {})
            sessions.append({
                "id": session.get("id"),
                "title": session.get("title"),
                "updated_at": session.get("updated_at"),
            })

        # 最近更新的排前面,resume 列表更顺手
        sessions.sort(key=lambda s: s["updated_at"] or "", reverse=True)
        return sessions
