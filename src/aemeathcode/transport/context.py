from asyncio import StreamWriter
from dataclasses import dataclass

@dataclass
class RequestContext:
    params: dict
    writer: StreamWriter
    request_id:str

