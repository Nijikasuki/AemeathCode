"""两级配置加载(项目级 .aemeath/.env 优先、全局 ~/.config/aemeath/.env 兜底)+ 必填体检。

重点测【优先级顺序】:python-dotenv 默认 override=False,写反了不会报错,只会静默
让全局永远赢 —— 这种"错了也不吭声"的地方最该拿测试钉住。
"""
import os

from aemeathcode.core.config import ensure_data_dir, get_config, load_env, missing_required

_MANAGED = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "AEMEATH_LLM_DEFAULT_MODEL",
    "AEMEATH_MAX_STEPS",
)


def _isolate(monkeypatch, tmp_path):
    """把两级配置位都指进 tmp_path,并清掉进程里可能残留的真实配置。"""
    for name in _MANAGED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)          # 项目级配置 = 这里的 .aemeath/.env
    return tmp_path / "config" / "aemeath" / ".env"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_project_env_wins_and_global_fills_the_gaps(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    _write(tmp_path / ".aemeath" / ".env", "AEMEATH_LLM_DEFAULT_MODEL=from-project\n")
    _write(global_env, "AEMEATH_LLM_DEFAULT_MODEL=from-global\nANTHROPIC_API_KEY=sk-global\n")

    load_env()

    assert os.environ["AEMEATH_LLM_DEFAULT_MODEL"] == "from-project"  # 两边都有 → 项目级赢
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-global"             # 只有全局有 → 兜底生效


def test_global_alone_is_enough(tmp_path, monkeypatch):
    # 全局装完就能用:当前目录压根没有 .env 也照样读得到配置
    global_env = _isolate(monkeypatch, tmp_path)
    _write(global_env, "ANTHROPIC_API_KEY=sk-global\nAEMEATH_LLM_DEFAULT_MODEL=m\n")

    load_env()

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-global"


def test_shell_env_beats_both_files(tmp_path, monkeypatch):
    # 真·环境变量在 load 之前就存在,override=False 让它比两个文件都硬
    global_env = _isolate(monkeypatch, tmp_path)
    _write(tmp_path / ".aemeath" / ".env", "AEMEATH_LLM_DEFAULT_MODEL=from-project\n")
    _write(global_env, "AEMEATH_LLM_DEFAULT_MODEL=from-global\n")
    monkeypatch.setenv("AEMEATH_LLM_DEFAULT_MODEL", "from-shell")

    load_env()

    assert os.environ["AEMEATH_LLM_DEFAULT_MODEL"] == "from-shell"


def test_user_own_dotenv_at_project_root_is_never_read(tmp_path, monkeypatch):
    """安全边界:用户自己项目根的 ./.env 一律不碰。

    load_dotenv 会把文件里【每一个】变量塞进本进程环境,而 daemon 有 bash 工具、
    子进程继承环境 —— 读它等于把人家的密钥灌进一个由 LLM 指挥执行 shell 的进程。"""
    _isolate(monkeypatch, tmp_path)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    _write(tmp_path / ".env", "STRIPE_SECRET_KEY=sk_live_dont_touch\nAEMEATH_LLM_DEFAULT_MODEL=hijacked\n")

    load_env()

    assert "STRIPE_SECRET_KEY" not in os.environ
    assert os.environ.get("AEMEATH_LLM_DEFAULT_MODEL") is None


def test_ensure_data_dir_drops_a_self_ignoring_gitignore(tmp_path, monkeypatch):
    # 目录里会有 API key,而用户项目未必 gitignore 了 .aemeath/ —— 让它自己带一张
    _isolate(monkeypatch, tmp_path)

    data_dir = ensure_data_dir()

    assert (data_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_ensure_data_dir_keeps_an_existing_gitignore(tmp_path, monkeypatch):
    # 用户改过就别覆盖他
    _isolate(monkeypatch, tmp_path)
    _write(tmp_path / ".aemeath" / ".gitignore", "!keep-me\n")

    ensure_data_dir()

    assert (tmp_path / ".aemeath" / ".gitignore").read_text(encoding="utf-8") == "!keep-me\n"


def test_missing_required_reports_both_when_nothing_configured(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    assert missing_required() == ["ANTHROPIC_API_KEY", "AEMEATH_LLM_DEFAULT_MODEL"]


def test_missing_required_empty_when_configured(tmp_path, monkeypatch):
    global_env = _isolate(monkeypatch, tmp_path)
    _write(global_env, "ANTHROPIC_API_KEY=sk-x\nAEMEATH_LLM_DEFAULT_MODEL=m\n")
    assert missing_required() == []


def test_blank_value_counts_as_missing(tmp_path, monkeypatch):
    # 设成空串/空白 = 没设,别让"看起来有这一行"骗过体检
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    monkeypatch.setenv("AEMEATH_LLM_DEFAULT_MODEL", "m")
    assert missing_required() == ["ANTHROPIC_API_KEY"]


def test_optional_vars_are_not_required(tmp_path, monkeypatch):
    # BASE_URL 不设 = 走官方端点,是正常用法,不该拦启动
    global_env = _isolate(monkeypatch, tmp_path)
    _write(global_env, "ANTHROPIC_API_KEY=sk-x\nAEMEATH_LLM_DEFAULT_MODEL=m\n")
    assert "ANTHROPIC_BASE_URL" not in missing_required()


def test_max_steps_falls_back_to_default(tmp_path, monkeypatch):
    # 回归:以前是 int(os.environ.get(...)),没设就 int(None) 直接把 daemon 崩在启动阶段
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("AEMEATH_LLM_DEFAULT_MODEL", "m")
    assert get_config().max_steps == 25


def test_max_steps_env_overrides_default(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("AEMEATH_LLM_DEFAULT_MODEL", "m")
    monkeypatch.setenv("AEMEATH_MAX_STEPS", "7")
    assert get_config().max_steps == 7
