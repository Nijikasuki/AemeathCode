"""首次配置向导:别人 pipx 装完 aemeath、还没配 .env 就跑,不该甩 traceback。

心智:**配置校验必须发生在前端、在拉起 daemon 之前**。daemon 是 headless 的
(bootstrap 把它的 stdout/stderr 重定向进 .aemeath/core.log 了),它就算发现缺配置
也没法问人 —— 前端只会看到"它没起来",看不到"为什么"。只有前端手里有终端。

顺带:先校验再拉 daemon,首次配置这条路上根本不存在"重启 daemon"的问题 ——
daemon 是配完之后才出生的,天生读到新配置。重启只在 `aemeath init` 改配置时才需要。
"""
import os
import stat
import sys
from pathlib import Path

from aemeathcode.core.config import (
    REQUIRED_ENV_VARS,
    ensure_data_dir,
    get_data_dir,
    get_global_env_path,
    missing_required,
)

# 向导问的项:(env 变量名, 标题, 提示语)。是否必填从 REQUIRED_ENV_VARS 推,别两处各写一份。
_QUESTIONS = [
    ("ANTHROPIC_API_KEY", "API Key", "你的 LLM 服务商密钥"),
    ("ANTHROPIC_BASE_URL", "Base URL", "Anthropic 兼容端点;留空 = 官方 api.anthropic.com"),
    ("AEMEATH_LLM_DEFAULT_MODEL", "模型名", "如 claude-sonnet-4-5 / deepseek-v4-flash"),
]


def _mask(value: str) -> str:
    """回显已有值时给密钥打码:只留头尾,中间抹掉。"""
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:6]}…{value[-4:]}"


def _write_env(path: Path, values: dict[str, str]) -> None:
    """把 values 合并进 .env 文件。

    只改对应的 key 行,注释、无关变量、用户手写的排版一律原样保留 —— 绝不整个 rewrite
    吃掉别人的内容。重复 key 全部替换(dotenv 里最后一条赢,只改第一条会被后面的旧值盖掉)。"""
    if not values:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    replaced = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()   # 注释行 "# X=1" 切出来是 "# X",不会误命中
        if key in values:
            lines[i] = f"{key}={values[key]}"
            replaced.add(key)
    for key, value in values.items():
        if key not in replaced:
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)   # 0600:里面是 API key,别让同机器别的用户读走


def _is_secret(name: str) -> bool:
    """要不要打码回显。按【变量名】判,不按提示文案判 —— 文案是给人看的,会改。"""
    return any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))


def _ask(name: str, title: str, hint: str, current: str, required: bool, index: int, total: int) -> str | None:
    """问一项。有现值就展示并允许直接回车沿用;必填项空着会重问。None = 用户放弃。

    用同步 input() 而不是 CLI 那套异步 _read_line:向导跑在 asyncio.run 之前,压根没有
    事件循环。(之前踩的 input() locale 解码坑是中文 goal 引起的,配置项都是 ASCII,安全。)"""
    shown = _mask(current) if (current and _is_secret(name)) else current
    print(f"\n  {index}/{total}  {title}")
    print(f"        {hint}")
    if current:
        print(f"        当前:{shown}(直接回车沿用)")

    while True:
        try:
            answer = input("      > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer:
            return answer
        if current or not required:
            return current      # 回车沿用现值;可选项没现值就是空
        print("        ⚠️  这项是必填的,请输入(放弃请按 Ctrl+D)")


def run_wizard(local: bool = False) -> bool:
    """跑配置向导。返回 True = 已写入,False = 用户中途放弃。

    默认写全局:凭证回答的是"我是谁、我用哪家 LLM",一台机器一份就够;写项目级会导致
    每换一个目录就重问一次,而且 API key 在每个用过的项目里各留一份。
    local=True 才写 .aemeath/.env,那是"这个项目要特殊对待什么"(换模型 / 换 key)。"""
    # 项目级要先 ensure:光靠 _write_env 的 mkdir 会建出一个【没有自我忽略 .gitignore】的
    # .aemeath/,而马上就要往里写 API key
    path = (ensure_data_dir() / ".env") if local else get_global_env_path()
    print("\n" + "─" * 56)
    print("  AemeathCode 配置向导" + ("(仅本项目)" if local else ""))
    print(f"  将写入:{path}")
    print("─" * 56)

    answers: dict[str, str] = {}
    for i, (name, title, hint) in enumerate(_QUESTIONS, start=1):
        value = _ask(
            name, title, hint,
            current=os.environ.get(name, "").strip(),
            required=name in REQUIRED_ENV_VARS,
            index=i, total=len(_QUESTIONS),
        )
        if value is None:
            print("\n  已取消,没有写入任何配置。")
            return False
        if value:
            answers[name] = value
        # 留空的可选项【不写】:比如 ANTHROPIC_BASE_URL= 空串会被 SDK 当成"显式指定了空地址",
        # 比不设它更糟 —— 不设才会回落到官方端点。

    _write_env(path, answers)
    # 关键一步:把新值同步进本进程的 os.environ。
    # 不做的话有个不报错的坑:前端待会儿 Popen 拉 daemon,子进程【继承的是父进程这份陈旧的
    # environ】,而 daemon 自己的 load_env() 是 override=False —— 一看"已经有值了"就不覆盖,
    # 新配置对 daemon 完全无效,而且全程没有任何报错。
    os.environ.update(answers)

    print(f"\n  ✅ 已保存到 {path}")
    return True


def print_manual_help() -> None:
    print(
        "\n  手动配置(二选一):\n"
        f"    · 全局(推荐,装一次到处能用):{get_global_env_path()}\n"
        f"    · 项目级(覆盖全局):{get_data_dir() / '.env'}\n"
        "\n  至少需要这两项:\n"
        "    ANTHROPIC_API_KEY=sk-...\n"
        "    AEMEATH_LLM_DEFAULT_MODEL=claude-sonnet-4-5\n"
        "\n  完整变量见项目里的 .env.example。随时可以重跑向导:aemeath init\n"
    )


def ensure_config() -> None:
    """需要 LLM 的命令跑之前调一次:配置齐了直接过,缺了就弹向导;仍然缺就打印指引后退出。"""
    missing = missing_required()
    if not missing:
        return

    print(f"\n  ⚠️  还没配置好,缺少:{', '.join(missing)}")
    if not run_wizard() or missing_required():
        print_manual_help()
        sys.exit(1)
