"""TaskManager 的单元测试:create/list/get/update(per-run 的任务白板)。"""
from aemeathcode.core.task.manager import TaskManager


def test_create_assigns_id_and_pending():
    tm = TaskManager()
    t = tm.create("写测试")
    assert t.content == "写测试"
    assert t.status == "pending"       # 新建默认 pending
    assert tm.get(t.id) is t


def test_ids_increment():
    tm = TaskManager()
    a = tm.create("a")
    b = tm.create("b")
    assert a.id != b.id                # 各自发号,不重复
    assert [t.content for t in tm.list()] == ["a", "b"]


def test_update_status():
    tm = TaskManager()
    t = tm.create("x")
    tm.update(t.id, "completed")
    assert tm.get(t.id).status == "completed"


def test_get_unknown_returns_none():
    assert TaskManager().get(999) is None
