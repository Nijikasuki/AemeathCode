import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# 真·必填:缺了 agent 根本跑不起来,前端会在拉 daemon 之前拦下来弹向导。
# 其余变量要么有合理默认(MAX_STEPS/PORT/LOG_LEVEL…),要么纯可选(BASE_URL/压缩三件套),
# 一律不进这张表 —— 别拿可选项绑架启动。
REQUIRED_ENV_VARS = ("ANTHROPIC_API_KEY", "AEMEATH_LLM_DEFAULT_MODEL")


class Config(BaseModel):
    host: str = '127.0.0.1'
    port: int = 9999
    log_level: str = "INFO"
    model: str
    max_steps: int = 25
    show_thinking: bool = True   # UI 是否显示 thinking(纯显示偏好;daemon 照常发,trace 不受影响)


def get_global_env_path() -> Path:
    """全局配置位:~/.config/aemeath/.env(遵循 XDG,可用 XDG_CONFIG_HOME 改)。

    存在的意义:aemeath 可以被 pipx/uv tool 装成全局命令,但配置却只从"当前目录"找,
    心智是矛盾的 —— 装一次就该到处能用。"""
    root = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(root) / "aemeath" / ".env"


def load_env() -> None:
    """两级配置加载的单一入口:项目级 .aemeath/.env 优先,全局 ~/.config/aemeath/.env 兜底。

    ⚠️ 加载顺序是反直觉的:python-dotenv 默认 override=False(已存在的变量不覆盖),
    所以必须【先加载优先级高的】,后加载的只能填空补缺。写反了全局永远赢、项目级失效。
    (真正的 shell 环境变量比两者都先存在,所以它优先级最高 —— 这也是 override=False 换来的。)

    ⚠️ 项目级读 .aemeath/.env 而【不是】用户项目根的 ./.env。理由是安全,不只是防重名:
    load_dotenv 会把那个文件里的每一个变量都塞进本进程环境,而 daemon 有 bash 工具、
    子进程继承环境 —— 读用户的 ./.env 等于把人家的 DATABASE_URL / STRIPE_KEY 一并
    灌进一个由 LLM 指挥执行 shell 的进程里。只读我们自己的文件,这个洞根本不存在。"""
    load_dotenv(_data_dir_raw() / ".env")   # ① 项目级 .aemeath/.env —— 优先
    load_dotenv(get_global_env_path())      # ② 全局:只填 ① 没给的项


def missing_required() -> list[str]:
    """体检:返回缺失的必填环境变量名,全齐则空列表。

    只报告,不抛异常、不打印、不退出 —— 拿它去弹向导还是直接报错,是调用方的决定
    (同 PermissionResult 的品味:返回结果让上层决策,而不是自己抛异常替上层拍板)。"""
    load_env()
    return [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]


def get_address() -> tuple[str, int]:
    """daemon 监听地址(host, port)的单一来源。

    轻量:只读 AEMEATH_HOST/AEMEATH_PORT,不依赖 model/max_steps —— 好让纯连接的
    命令(探活 / stop / 前端连 daemon)用它时,不被 LLM 相关的必填配置绊住。"""
    load_env()
    host = os.environ.get("AEMEATH_HOST", "127.0.0.1")
    port = int(os.environ.get("AEMEATH_PORT", 9999))
    return host, port


def get_config():
    load_env()
    host, port = get_address()   # 复用单一来源,daemon 与前端读到的地址永远一致
    return Config(
        host=host,
        port=port,
        log_level=os.environ.get("AEMEATH_LOG_LEVEL", "INFO"),
        model=os.environ.get("AEMEATH_LLM_DEFAULT_MODEL"),
        # `or 25` 同时兜住"没设"和"设成空串";之前写 int(os.environ.get(...)) 缺了直接 int(None) 崩
        max_steps=int(os.environ.get("AEMEATH_MAX_STEPS") or 25),
        show_thinking=os.environ.get("AEMEATH_SHOW_THINKING", "true").strip().lower() in ("1", "true", "yes", "on"),
    )


def _data_dir_raw() -> Path:
    """算数据目录,【绝不调用 load_env】。

    因为项目级配置文件本身就住在这个目录里(.aemeath/.env),要是这里回头去 load_env,
    load_env 又要问这里 —— 无限递归。所以定死一条规则:AEMEATH_DATA_DIR 只认真正的
    shell 环境变量。它决定所有数据(含配置文件自己)放在哪,不可能再由那些文件里的
    一行来决定,那是鸡生蛋。"""
    return Path(os.environ.get("AEMEATH_DATA_DIR", ".aemeath"))


def get_data_dir() -> Path:
    """所有本地数据(配置 / sessions / run / note.md / permissions.json)的根目录。
    纯读,不建目录 —— aemeath trace 这类只看不写的命令不该顺手拉出一个空目录。"""
    return _data_dir_raw()


def ensure_data_dir() -> Path:
    """要往里写东西时用:建目录,并保证里面有一张自我忽略的 .gitignore。

    那张 .gitignore 内容就一个 `*`,让整个目录对 git 隐身。原因:项目级配置文件里有
    API key,而用户自己的项目未必 gitignore 了 .aemeath/ —— 与其指望他记得加,
    不如让这个目录自己带着。"""
    data_dir = _data_dir_raw()
    data_dir.mkdir(parents=True, exist_ok=True)
    gitignore = data_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
    return data_dir
