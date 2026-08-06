"""Agent profiles（角色）—— 从 toml 加载"子 agent 以什么身份跑"的定义。

一个 profile = 一套 system_prompt + 工具白名单 + 模型。喂给 subagent:
spawn_agent(goal=..., agent="reviewer") 就让子 agent 按 reviewer 这套跑。

设计:
* 一个 toml 一个角色,name 缺省用文件名(reviewer.toml → "reviewer")。
* tools/model 都可省:tools 省 = 用默认工具集(全部减 spawn_agent);model 省 = 用默认模型。
* loader 不校验工具名是否存在(不耦合 registry);写错的名字在 registry.subset 那步被静默丢弃。
"""
import tomllib
from pathlib import Path

from pydantic import BaseModel

BUILTIN_DIR = Path(__file__).parent / "builtin"


class AgentProfile(BaseModel):
    name: str
    system_prompt: str
    tools: list[str] | None = None   # None = 默认工具集(全部减 spawn_agent)
    model: str | None = None         # None = 用默认模型(即父的模型)


def _load_one(path: Path) -> AgentProfile:
    with path.open("rb") as f:            # tomllib 只吃二进制流
        data = tomllib.load(f)
    data.setdefault("name", path.stem)    # name 缺省用文件名,避免和文件名对不上
    return AgentProfile(**data)


class ProfileStore:
    """把一个目录下所有 *.toml 角色读进内存,按 name 取。base_dir 可注入,方便测试。"""

    def __init__(self, base_dir: Path = BUILTIN_DIR) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        if base_dir.exists():
            for path in sorted(base_dir.glob("*.toml")):
                profile = _load_one(path)
                self._profiles[profile.name] = profile

    def get(self, name: str) -> AgentProfile | None:
        return self._profiles.get(name)

    def names(self) -> list[str]:
        return list(self._profiles.keys())
