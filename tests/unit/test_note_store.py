"""NoteStore 的单元测试:append/load(agent 自写的全局便签,一行一条)。"""
from aemeathcode.core.memory.note import NoteStore


def test_append_then_load(tmp_path):
    store = NoteStore(base_dir=tmp_path)
    store.append("记住 A")
    store.append("记住 B")
    assert store.load() == ["记住 A", "记住 B"]      # 顺序保留、逐条读回


def test_load_empty_when_no_file(tmp_path):
    # 还没写过任何便签 → load 返回空列表(不炸)
    assert NoteStore(base_dir=tmp_path).load() == []
