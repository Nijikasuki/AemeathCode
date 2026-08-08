"""SkillStore 的单元测试:frontmatter 解析 + 用户目录覆盖 + catalog。

【新概念:fixture `tmp_path`】
pytest 内置的 `tmp_path` 是一个"每个测试独享的临时目录"(pathlib.Path)。
把它写成测试函数的【参数】,pytest 就自动把一个干净的临时目录传进来,测完自动删。
测"读文件的代码"就用它造几个文件,不污染真项目、测试之间也互不干扰。
"""
from aemeathcode.core.skills.loader import SkillStore


def _write(directory, name: str, text: str):
    (directory / name).write_text(text, encoding="utf-8")


def test_skill_parses_frontmatter(tmp_path):
    _write(tmp_path, "summarize.md", "---\ndescription: 压缩要点\n---\n# 正文\n步骤一")
    s = SkillStore(base_dir=tmp_path).get("summarize")
    assert s.name == "summarize"        # name 从文件名派生
    assert s.description == "压缩要点"    # description 来自 frontmatter
    assert "步骤一" in s.body            # 正文是 --- 之后的部分


def test_skill_without_frontmatter(tmp_path):
    _write(tmp_path, "plain.md", "# 只有正文,没有 frontmatter")
    s = SkillStore(base_dir=tmp_path).get("plain")
    assert s.description == ""                    # 没 frontmatter → 空描述
    assert "只有正文" in s.body


def test_catalog_text_lists_name_and_desc(tmp_path):
    _write(tmp_path, "a.md", "---\ndescription: 甲技能\n---\n正文")
    text = SkillStore(base_dir=tmp_path).catalog_text()
    assert "a" in text and "甲技能" in text       # 目录里有 name + 简介


def test_user_dir_overrides_builtin(tmp_path):
    """同名时用户目录覆盖内置 —— skills 可定制的关键。"""
    builtin = tmp_path / "builtin"; builtin.mkdir()
    user = tmp_path / "user"; user.mkdir()
    _write(builtin, "s.md", "---\ndescription: 内置版\n---\n内置正文")
    _write(user, "s.md", "---\ndescription: 用户版\n---\n用户正文")

    store = SkillStore(base_dir=builtin, user_dir=user)
    assert store.get("s").description == "用户版"   # user 覆盖 builtin
