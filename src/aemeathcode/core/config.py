import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

class Config(BaseModel):
    host: str = '127.0.0.1'
    port: int = 9999
    log_level: str = "INFO"
    model: str
    max_steps: int
    show_thinking: bool = True   # UI 是否显示 thinking(纯显示偏好;daemon 照常发,trace 不受影响)

def get_address() -> tuple[str, int]:
    """daemon 监听地址(host, port)的单一来源。

    轻量:只读 AEMEATH_HOST/AEMEATH_PORT,不依赖 model/max_steps —— 好让纯连接的
    命令(探活 / stop / 前端连 daemon)用它时,不被 LLM 相关的必填配置绊住。"""
    load_dotenv()
    host = os.environ.get("AEMEATH_HOST", "127.0.0.1")
    port = int(os.environ.get("AEMEATH_PORT", 9999))
    return host, port


def get_config():
    load_dotenv()
    host, port = get_address()   # 复用单一来源,daemon 与前端读到的地址永远一致
    return Config(
        host=host,
        port=port,
        log_level=os.environ.get("AEMEATH_LOG_LEVEL", "INFO"),
        model=os.environ.get("AEMEATH_LLM_DEFAULT_MODEL"),
        max_steps=int(os.environ.get("AEMEATH_MAX_STEPS")),
        show_thinking=os.environ.get("AEMEATH_SHOW_THINKING", "true").strip().lower() in ("1", "true", "yes", "on"),
    )

def get_data_dir() -> Path:
    """所有本地数据(sessions / run / note.md / permissions.json)的根目录。
    轻量:只读 AEMEATH_DATA_DIR(默认 .aemeath),不依赖 LLM 相关配置,
    所以 aemeath trace 这类命令用它也不会被迫要 model/max_steps。"""
    load_dotenv()
    return Path(os.environ.get("AEMEATH_DATA_DIR", ".aemeath"))
