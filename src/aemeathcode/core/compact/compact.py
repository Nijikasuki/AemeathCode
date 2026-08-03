import json
import os

DEFAULT_KEEP_BUDGET = 10000

def keep_budget() -> int:
    # 尾巴保留预算(token)。env 覆盖 → 默认,方便测试时调小逼出压缩。
    env = os.environ.get("AEMEATH_KEEP_BUDGET")
    return int(env) if env else DEFAULT_KEEP_BUDGET

SUMMARY_PROMPT ="""
你是 AemeathCode 的上下文压缩器（Context Compactor）。

你的任务是将之前的对话压缩成一份紧凑、准确的工作记忆。

压缩完成后，原始对话将被丢弃，Agent 后续只能看到：
1. 你的总结
2. 最近保留的几轮消息

因此，你必须保留所有能够让 Agent 无缝继续工作的关键信息。

请按照以下格式输出：

【任务目标】
用户最终希望完成什么。

【当前进度】
已经完成了哪些工作。

【当前状态】
当前代码、项目、环境或任务所处的状态。

【重要上下文】
包括但不限于：
- 用户的重要要求
- 已做出的设计决策
- 文件路径
- 类名、函数名、变量名
- API 或工具调用方式
- Bug 及原因
- 已确认的重要事实
- 后续工作依赖的信息

【待完成事项】
仍然需要完成的任务。

【下一步】
Agent 接下来最应该执行的一步。

要求：

- 只保留事实，不要猜测。
- 不要编造任何不存在的信息。
- 删除寒暄、闲聊、重复内容和已经没有价值的讨论。
- 删除中间推理过程，只保留最终结论。
- 尽量精简，但不能遗漏任何会影响后续工作的关键信息。
- 输出内容不要使用 Markdown 代码块，只输出总结内容。"""

class Compactor:
    def __init__(self,provider):
        self.provider = provider

    async def compact(self,ctx)->None:
        budget = keep_budget()
        kept_tokens = 0
        keep_len = 0
        for msg in reversed(ctx.messages):
            if kept_tokens >= budget:
                break
            kept_tokens += self._estimate_tokens(msg.get("content"))
            keep_len +=1

        if keep_len == len(ctx.messages): ##历史还没有长到需要切
            return

        if ctx.messages[-keep_len].get("role") == "user": ##防止出现孤儿 tool_result
            keep_len += 1

        old_messages = ctx.messages[:-keep_len]
        recent_messages = ctx.messages[-keep_len:]
        resp = await self.provider.complete(system=SUMMARY_PROMPT,messages=old_messages)
        summary = [{"role": "user", "content": resp}]
        ctx.messages = summary+recent_messages


    def _estimate_tokens(self, content) -> int:
        # 本地粗估:字符数 / 4。content 可能是 str(纯文本)或 block 列表
        # (tool_use/tool_result/text 混合),后者整体序列化成文本再估。
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, ensure_ascii=False)
        return len(text) // 4
