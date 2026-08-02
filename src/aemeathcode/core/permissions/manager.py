from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aemeathcode.core.permissions import policy
from aemeathcode.core.permissions.storage import PermissionStore

if TYPE_CHECKING:
    # 只为类型标注,运行时不 import → 断开 context→manager→tools.base→context 的循环
    from aemeathcode.agent.tools.base import BaseTool

_DETAIL_MAX = 80   # 给人看的审批详情截断上限,防超长命令/路径把提示框撑爆


@dataclass
class PermissionResult:
    """审批结论。allowed=是否放行;reason=拒绝原因(放行时可空),给 invoke_tool 拼进
    ToolResult,让 LLM 知道"为什么没跑成",而不是只拿到一个光秃秃的 True/False。"""
    allowed: bool
    reason: str = ""


class PermissionsManager:
    def __init__(self, storage: PermissionStore):
        self._storage = storage

    async def check(self, tool: BaseTool, params, approver, run_id) -> PermissionResult:
        d = policy.evaluate(tool.name, params)
        if d == "allow":
            return PermissionResult(True)
        if d == "deny":
            return PermissionResult(False, f"策略拒绝:{tool.name} 命中危险规则")

        # d == "ask":先看用户以前有没有教过(allow_always 落过盘)
        key = tool.permission_key(params)
        if self._storage.load().get(key) == "allow":
            return PermissionResult(True, "已记住的授权")

        # 没教过 → 反向问用户
        detail = tool.permission_detail(params)
        if len(detail) > _DETAIL_MAX:
            detail = detail[:_DETAIL_MAX] + "…"
        decision = await approver.ask(tool.name, detail, run_id)
        if decision == "deny":
            return PermissionResult(False, "用户拒绝了本次操作")
        if decision == "allow_always":
            self._storage.remember(key=key, decision="allow")
            return PermissionResult(True)
        # allow_once
        return PermissionResult(True)
