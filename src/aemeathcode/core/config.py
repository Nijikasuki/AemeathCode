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

def get_config():
    load_dotenv()
    return Config(
        host=os.environ.get("AEMEATH_HOST", "127.0.0.1"),
        port=os.environ.get("AEMEATH_PORT", 9999),
        log_level=os.environ.get("AEMEATH_LOG_LEVEL", "INFO"),
        model=os.environ.get("AEMEATH_LLM_DEFAULT_MODEL"),
        max_steps=int(os.environ.get("AEMEATH_MAX_STEPS")),
    )

def get_data_dir() -> Path:
    """所有本地数据(sessions / run / note.md / permissions.json)的根目录。
    轻量:只读 AEMEATH_DATA_DIR(默认 .aemeath),不依赖 LLM 相关配置,
    所以 aemeath trace 这类命令用它也不会被迫要 model/max_steps。"""
    load_dotenv()
    return Path(os.environ.get("AEMEATH_DATA_DIR", ".aemeath"))
