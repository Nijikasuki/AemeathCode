"""SessionManager 的单元测试:create/get/add_run/build_history。

SessionStore 的 base_dir 用 tmp_path 注入 → 落盘落到临时目录,测完自动清理、互不干扰。
"""
from aemeathcode.core.session.manager import SessionManager
from aemeathcode.core.session.store import SessionStore


def _mgr(tmp_path):
    return SessionManager(SessionStore(base_dir=tmp_path / "sessions"))


def test_create_then_get(tmp_path):
    mgr = _mgr(tmp_path)
    runtime = mgr.create("multi_turn")
    sid = runtime.session.id
    assert mgr.get(sid) is runtime            # 建完就能按 id 取回内存活状态
    assert mgr.get("no-such-id") is None


def test_add_run_appends_run_id(tmp_path):
    mgr = _mgr(tmp_path)
    sid = mgr.create("multi_turn").session.id
    mgr.add_run(sid, "run-1")
    assert "run-1" in mgr.get(sid).session.run_ids   # run_ids 索引记上了


def test_build_history_empty_for_fresh_session(tmp_path):
    mgr = _mgr(tmp_path)
    sid = mgr.create("multi_turn").session.id
    assert mgr.build_history(sid) == []        # 还没有任何 run → 历史为空
