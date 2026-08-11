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

class EventEnvelope(BaseModel):
    kind :Literal["event"] = "event"
    event : dict

def make_error(id,code,message):
    return JsonRpcError(id = id,error = JsonRpcErrorObject(code = code,message = message))

class AskEnvelope(BaseModel):
    kind :Literal["ask"] = "ask"
    approval_id: str
    tool_name: str
    detail: str          # 给人看的一句话摘要,会被截断(manager._DETAIL_MAX)
    # 完整参数。detail 截断后不够审批(比如 write_file 要看全文),前端靠这个渲染预览。
    # 【自带而不是让前端去事件流里捞】:审批是一次独立的请求,请求该自己说清求的是什么。
    params: dict = Field(default_factory=dict)
    run_id: str

class ReplyEnvelope(BaseModel):
    kind :Literal["reply"] = "reply"
    approval_id: str
    decision: Literal["allow_once","allow_always","deny"]