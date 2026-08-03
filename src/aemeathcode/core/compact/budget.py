import os

from aemeathcode.agent.llm.models import model_info, output_budget
from aemeathcode.agent.llm.types import UsageStats

# 安全垫:除了给模型输出留 output_budget,再多留一点(估算不准 / 下一发工具结果)。
SAFETY_MARGIN = 2000

def should_compact(usage:UsageStats,model:str)->bool:
    # 预留 = 我们请求的输出预算(provider 发的 max_tokens 同源)+ 安全垫。请求多少就留多少。
    return context_used(usage=usage) >= min(context_window(model=model) - SAFETY_MARGIN - output_budget(model=model),context_window(model=model)*0.85)

def context_window(model:str)->int:
    env = os.environ.get("AEMEATH_CONTEXT_WINDOW")
    if env:
        return int(env)
    return model_info(model).context_window

def context_used(usage:UsageStats)->int:
    return usage.input_tokens + usage.output_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens