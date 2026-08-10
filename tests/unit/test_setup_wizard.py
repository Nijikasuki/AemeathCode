"""首次配置向导:.env 合并写入 + 交互流程。"""
import os
import stat

from aemeathcode.cli.setup import _write_env, run_wizard

_MANAGED = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "AEMEATH_LLM_DEFAULT_MODEL")


def _isolate(monkeypatch, tmp_path):
    for name in _MANAGED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AEMEATH_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "proj").mkdir(exist_ok=True)   # --local 的落点:cwd 下的 .aemeath/
    return tmp_path / "aemeath" / ".env"


# ── _write_env:合并,不是覆盖 ─────────────────────────────────────────────

def test_creates_parent_dirs_and_file(tmp_path):
    path = tmp_path / "nested" / ".env"
    _write_env(path, {"A": "1"})
    assert path.read_text(encoding="utf-8") == "A=1\n"


def test_preserves_comments_and_unrelated_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# 我手写的注释\nOTHER=keep\nA=old\n", encoding="utf-8")

    _write_env(path, {"A": "new", "B": "added"})

    assert path.read_text(encoding="utf-8").splitlines() == [
        "# 我手写的注释", "OTHER=keep", "A=new", "B=added",
    ]


def test_replaces_every_duplicate_not_just_the_first(tmp_path):
    # dotenv 里重复 key 是【最后一条赢】,只改第一条会被后面的旧值悄悄盖回去
    path = tmp_path / ".env"
    path.write_text("A=old1\nA=old2\n", encoding="utf-8")

    _write_env(path, {"A": "new"})

    assert path.read_text(encoding="utf-8").splitlines() == ["A=new", "A=new"]


def test_commented_out_line_is_not_mistaken_for_an_assignment(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# A=disabled\n", encoding="utf-8")

    _write_env(path, {"A": "new"})

    assert path.read_text(encoding="utf-8").splitlines() == ["# A=disabled", "A=new"]


def test_file_is_owner_readable_only(tmp_path):
    path = tmp_path / ".env"
    _write_env(path, {"ANTHROPIC_API_KEY": "sk-secret"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600   # 里面是密钥


# ── run_wizard:交互 ──────────────────────────────────────────────────────

def test_writes_answers_and_skips_blank_optional(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    answers = iter(["sk-typed", "", "my-model"])       # Base URL 留空
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    assert run_wizard() is True

    content = global_env.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=sk-typed" in content
    assert "AEMEATH_LLM_DEFAULT_MODEL=my-model" in content
    # 留空的可选项【不写】:ANTHROPIC_BASE_URL= 空串会被 SDK 当"显式指定了空地址",
    # 比不设它更糟 —— 不设才会回落到官方端点
    assert "ANTHROPIC_BASE_URL" not in content


def test_syncs_new_values_into_current_process_env(tmp_path, monkeypatch):
    # 不同步的话:待会儿 Popen 拉起的 daemon 继承的是父进程这份陈旧 environ,
    # 而 daemon 的 load_env() 是 override=False,一看"已经有值"就不覆盖 → 新配置静默失效
    _isolate(monkeypatch, tmp_path)
    answers = iter(["sk-typed", "https://api.example.com", "my-model"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    run_wizard()

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-typed"
    assert os.environ["AEMEATH_LLM_DEFAULT_MODEL"] == "my-model"


def test_enter_keeps_the_current_value(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-existing")
    answers = iter(["", "", "my-model"])               # 前两项直接回车
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    run_wizard()

    assert "ANTHROPIC_API_KEY=sk-existing" in global_env.read_text(encoding="utf-8")


def test_required_field_is_asked_again_when_left_blank(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    # 第一次回车(必填项没有现值 → 重问),第二次才给值
    answers = iter(["", "sk-typed", "", "my-model"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    assert run_wizard() is True
    assert "ANTHROPIC_API_KEY=sk-typed" in global_env.read_text(encoding="utf-8")


def test_local_writes_into_project_data_dir(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path / "proj")
    answers = iter(["sk-proj", "", "proj-model"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    assert run_wizard(local=True) is True

    project_env = tmp_path / "proj" / ".aemeath" / ".env"
    assert "AEMEATH_LLM_DEFAULT_MODEL=proj-model" in project_env.read_text(encoding="utf-8")
    assert not global_env.exists()          # --local 不该碰全局


def test_local_data_dir_gets_the_self_ignoring_gitignore(tmp_path, monkeypatch):
    # _write_env 自己的 mkdir 会建出一个没有 .gitignore 的 .aemeath/,而马上要往里写 key
    _isolate(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path / "proj")
    answers = iter(["sk-proj", "", "proj-model"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    run_wizard(local=True)

    assert (tmp_path / "proj" / ".aemeath" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_gives_up_cleanly_on_eof(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)

    def _eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)

    assert run_wizard() is False
    assert not global_env.exists()        # 放弃就是什么都不写
