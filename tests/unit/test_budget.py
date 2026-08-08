"""上下文压缩预算 budget 的单元测试。

【新概念:monkeypatch —— 临时替换/stub 依赖】
should_compact 依赖 context_window 和 output_budget 两个函数。要单独测"阈值判断"这段逻辑,
就用 pytest 的 `monkeypatch` 把这俩【临时换成固定值】(测完自动还原),这样阈值可控、结果确定。
monkeypatch.setenv 同理:临时设环境变量,测完自动清掉,不污染别的测试。
"""
from aemeathcode.agent.llm.types import UsageStats
from aemeathcode.core.compact.budget import context_used, context_window, should_compact
import aemeathcode.core.compact.budget as budget


def _usage(inp=0, out=0, cc=0, cr=0):
    return UsageStats(input_tokens=inp, output_tokens=out,
                      cache_creation_input_tokens=cc, cache_read_input_tokens=cr)


def test_context_used_sums_all_four_token_fields():
    # 水位 = 输入 + 输出 + 缓存创建 + 缓存读,四项都算(含 cache)
    assert context_used(_usage(inp=10, out=20, cc=3, cr=7)) == 40


def test_context_window_env_override(monkeypatch):
    monkeypatch.setenv("AEMEATH_CONTEXT_WINDOW", "12345")   # 临时设,测完自动还原
    assert context_window("any-model") == 12345


def test_should_compact_threshold(monkeypatch):
    # stub 掉两个依赖,把阈值算式隔离出来测:
    #   阈值 = min(window - SAFETY_MARGIN(2000) - output_budget, window*0.85)
    #        = min(100000 - 2000 - 30000, 85000) = min(68000, 85000) = 68000
    monkeypatch.setattr(budget, "context_window", lambda model: 100_000)
    monkeypatch.setattr(budget, "output_budget", lambda model: 30_000)

    assert should_compact(_usage(inp=67_999), "m") is False   # 差一点,不压
    assert should_compact(_usage(inp=68_000), "m") is True    # 到线,压
