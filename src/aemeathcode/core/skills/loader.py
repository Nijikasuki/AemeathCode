"""Skills —— 可复用的 md 指令包("操作手册")。

一个 skill = name + description + body(正文流程)。
* name 从文件名派生(summarize.md → "summarize")。
* description 来自可选的 frontmatter(md 顶部 --- 块里的 description: 一行),给模型看的目录。
* body 是正文(具体流程步骤),按需被 use_skill 工具加载进对话。

设计要点:**catalog(name+description,短)常驻 system 让模型知道有啥;body(长)只在
use_skill 调用时才加载** —— 这就是 skill "按需" 的实现,几十个 skill 也不撑爆每次的 prompt。

frontmatter 手解析(不引 pyyaml):只取一个 description,几行足够。
"""
from pathlib import Path

from pydantic import BaseModel

BUILTIN_DIR = Path(__file__).parent / "builtin"


class Skill(BaseModel):
    name: str
    description: str
    body: str


def _parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    description = ""
    body = text.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)          # ['', frontmatter, body];maxsplit=2 不碰正文里的 --- 分隔线
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    if key.strip() == "description":
                        description = val.strip()
            body = parts[2].strip()
    return Skill(name=path.stem, description=description, body=body)


class SkillStore:
    """把一个目录下所有 *.md 技能读进内存,按 name 取。base_dir 可注入,方便测试。"""

    def __init__(self, base_dir: Path = BUILTIN_DIR, user_dir: Path | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self._load_dir(base_dir)                          # 内置技能
        if user_dir is not None:
            user_dir.mkdir(parents=True, exist_ok=True)   # 建好目录,让用户知道往哪扔 .md
            self._load_dir(user_dir)                       # 用户技能;同名【覆盖】内置 → 可定制

    def _load_dir(self, d: Path) -> None:
        if not d.exists():
            return
        for path in sorted(d.glob("*.md")):
            skill = _parse(path)
            self._skills[skill.name] = skill              # 后加载的覆盖先加载的(user 覆盖 builtin)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def catalog_text(self) -> str:
        """给模型看的技能目录(name + description),常驻拼进 system。空则返回空串。"""
        if not self._skills:
            return ""
        lines = [f"- {s.name}:{s.description}" for s in self._skills.values()]
        return "# 可用技能(需要时用 use_skill 工具加载其正文,再照着做)\n" + "\n".join(lines)
