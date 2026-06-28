import os

from dotenv import load_dotenv
from pydantic import BaseModel

class Config(BaseModel):
    host: str = '127.0.0.1'
    port: int = 9999
    log_level: str = "INFO"

def get_config():
    load_dotenv()
    return Config(
        host=os.environ.get("AEMEATH_HOST", "127.0.0.1"),
        port=os.environ.get("AEMEATH_PORT", 9999),
        log_level=os.environ.get("AEMEATH_LOG_LEVEL", "INFO"),
    )
