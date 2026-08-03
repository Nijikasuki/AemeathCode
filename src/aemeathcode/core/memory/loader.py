from pathlib import Path

PROJECT_MEMORY_FILE = "AEMEATH.md"


def load_project_memory(data_dir: Path) -> str:
    """读项目记忆:人写的 AEMEATH.md(类似 Claude Code 的 CLAUDE.md),拼进 system prompt。

    与 note 是一对兄弟 —— note 是 agent 自己写的,项目记忆是人写的;都全局、都进 system。
    文件不存在或为空 → 返回 ''(没有就没有,loader 不报错)。
    """
    path = data_dir / PROJECT_MEMORY_FILE
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()
