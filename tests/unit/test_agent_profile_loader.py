"""ProfileStore(角色 toml 加载)的单元测试 —— 和 skills loader 一个模子。"""
from aemeathcode.core.agents.loader import ProfileStore


def _write(directory, name: str, text: str):
    (directory / name).write_text(text, encoding="utf-8")


def test_profile_loads_all_fields(tmp_path):
    _write(tmp_path, "reviewer.toml",
           'system_prompt = "审代码,只挑问题"\ntools = ["read_file", "list_dir"]\nmodel = "cheap"\n')
    p = ProfileStore(base_dir=tmp_path).get("reviewer")
    assert p.name == "reviewer"                 # name 从文件名派生
    assert p.system_prompt == "审代码,只挑问题"
    assert p.tools == ["read_file", "list_dir"]
    assert p.model == "cheap"


def test_profile_optional_fields_default_none(tmp_path):
    _write(tmp_path, "planner.toml", 'system_prompt = "只规划"\n')
    p = ProfileStore(base_dir=tmp_path).get("planner")
    assert p.tools is None       # 没写 → None(=用默认工具集)
    assert p.model is None       # 没写 → None(=用默认模型)


def test_unknown_profile_returns_none(tmp_path):
    assert ProfileStore(base_dir=tmp_path).get("does_not_exist") is None
