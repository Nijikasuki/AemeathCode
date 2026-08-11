"""PermissionsManager 往 approver 递什么。

重点在:审批请求要【自带完整参数】。detail 是给人看的一句话摘要、会被截断,
前端(TUI 审批面板)要渲染"将要写入的全文"就只能靠 params。
"""
from pathlib import Path

from aemeathcode.core.permissions.manager import PermissionsManager
from aemeathcode.core.permissions.storage import PermissionStore


class FakeTool:
    name = "write_file"

    def permission_key(self, params) -> str:
        return f"write_file:{params.get('path','')}"

    def permission_detail(self, params) -> str:
        return "写入 " + str(params.get("path", ""))


class SpyApprover:
    def __init__(self, decision: str = "deny"):
        self.decision = decision
        self.calls: list[tuple] = []

    async def ask(self, tool_name, detail, run_id, params=None):
        self.calls.append((tool_name, detail, run_id, params))
        return self.decision


async def test_ask_carries_full_params(tmp_path: Path):
    mgr = PermissionsManager(storage=PermissionStore(base_dir=tmp_path))
    approver = SpyApprover(decision="deny")
    params = {"path": "a.txt", "content": "x" * 2000}   # 比 _DETAIL_MAX 长得多

    result = await mgr.check(tool=FakeTool(), params=params, approver=approver, run_id="r1")

    assert result.allowed is False
    tool_name, detail, run_id, sent = approver.calls[0]
    assert tool_name == "write_file"
    assert run_id == "r1"
    assert sent == params            # 完整参数原样送到,没被 detail 的截断连累
    assert len(detail) <= 501        # detail 仍然是截断过的摘要


async def test_remembered_allow_skips_approver(tmp_path: Path):
    store = PermissionStore(base_dir=tmp_path)
    store.remember("write_file:a.txt")
    approver = SpyApprover()

    result = await PermissionsManager(storage=store).check(
        tool=FakeTool(), params={"path": "a.txt"}, approver=approver, run_id="r1")

    assert result.allowed is True
    assert approver.calls == []      # 教过一次就不再打扰
