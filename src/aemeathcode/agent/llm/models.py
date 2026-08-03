import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    context_window: int      # 上下文窗口(token),budget 用它判压缩
    max_output_tokens: int   # 模型物理上限(能力天花板)—— 只当"帽子",防止请求超过模型允许


# 值取模型官方数字,拿不准时窗口宁可写小、输出宁可写实(早压 > 撑爆)。
MODELS: dict[str, ModelInfo] = {
    "deepseek-v4-flash": ModelInfo(context_window=1000000, max_output_tokens=384000),
}

# 表里没有的未知模型落到这里 —— 保守值,宁可早压、宁可少吐。
DEFAULT_MODEL_INFO = ModelInfo(context_window=32000, max_output_tokens=4096)

# 每轮输出预算(policy,不是模型能力):我们实际给一个回答留的 token 空间。
# provider 用它当请求 max_tokens、budget 用它算 headroom —— 两处共用同一个数,
# 保证"请求多少就预留多少",绝不会授权了却没留位子。384K 那种理论极限不该直接用。
DEFAULT_OUTPUT_BUDGET = 32000


def model_info(model: str) -> ModelInfo:
    return MODELS.get(model, DEFAULT_MODEL_INFO)


def output_budget(model: str) -> int:
    # env 覆盖 → 默认预算,再用模型物理上限封顶(不能请求超过模型允许)。
    env = os.environ.get("AEMEATH_OUTPUT_BUDGET")
    desired = int(env) if env else DEFAULT_OUTPUT_BUDGET
    return min(desired, model_info(model).max_output_tokens)
