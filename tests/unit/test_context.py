"""ExecutionContext 的状态方法单元测试(不碰 services,所以 services 传 None 即可)。

这些方法是 run 的"状态机":拼初始消息、双写 messages/record、标成功失败、累加 token。
"""
from aemeathcode.agent.llm.types import LlmResponse, UsageStats
from aemeathcode.core.context import ExecutionContext


def _ctx(goal="hi"):
    # 只测状态方法,tasks/services 用不到 → 传 None(dataclass 不强制类型)
    return ExecutionContext(goal=goal, max_steps=5, run_id="r",
                            tasks=None, messages=[], services=None)


def test_post_init_seeds_goal_into_messages_and_record():
    ctx = _ctx("do X")
    assert ctx.messages == [{"role": "user", "content": "do X"}]
    assert ctx.record == [{"role": "user", "content": "do X"}]   # 两边都种下 goal


def test_add_assistant_message_dual_writes():
    ctx = _ctx()
    ctx.add_assistant_message([{"type": "text", "text": "hi"}])
    assert ctx.messages[-1] == {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}
    assert ctx.record[-1] == ctx.messages[-1]     # messages 和 record 同步双写


def test_mark_failed_and_is_done():
    ctx = _ctx()
    assert ctx.is_done() is False        # 初始 running
    ctx.mark_failed("boom")
    assert ctx.status == "error"
    assert ctx.reason == "boom"
    assert ctx.is_done() is True


def test_token_add_accumulates_and_ignores_none():
    ctx = _ctx()
    u = UsageStats(input_tokens=5, output_tokens=3, cache_creation_input_tokens=0, cache_read_input_tokens=2)
    ctx.token_add(LlmResponse(stop_reason="end_turn", usage=u))
    assert (ctx.total_input_tokens, ctx.total_output_tokens, ctx.total_cache_read) == (5, 3, 2)
    assert ctx.last_usage is u

    ctx.token_add(LlmResponse(stop_reason="end_turn", usage=None))   # usage=None 时不动
    assert ctx.total_input_tokens == 5
