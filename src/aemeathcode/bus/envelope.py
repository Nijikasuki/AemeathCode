from pydantic import BaseModel, Field
from typing import Any,Literal


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    method: str
    params: dict = Field(default_factory=dict)

class JsonRpcSuccess(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: Any

class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Any = None

class JsonRpcError(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None = None
    error: JsonRpcErrorObject

def make_error(id,code,message):
    return JsonRpcError(id = id,error = JsonRpcErrorObject(code = code,message = message))