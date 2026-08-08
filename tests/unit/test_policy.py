"""权限 policy.evaluate 的单元测试——安全相关,重点测"deny 优先于 allow"。

纯函数,给不同(tool, params)断言返回 allow/deny/ask。
"""
from aemeathcode.core.permissions.policy import evaluate


def test_readonly_tool_allow():
    assert evaluate("read_file", {}) == "allow"
    assert evaluate("list_dir", {}) == "allow"


def test_unknown_tool_defaults_ask():
    """没在表里的工具兜底 ask(比如 MCP 工具)。"""
    assert evaluate("some_random_tool", {}) == "ask"


def test_bash_safe_first_word_allow():
    """bash 首词在白名单(ls/cat/grep…)→ allow。"""
    assert evaluate("bash", {"command": "ls -la /tmp"}) == "allow"


def test_bash_default_ask():
    """bash 首词不在白名单、也不危险 → 默认 ask。"""
    assert evaluate("bash", {"command": "python train.py"}) == "ask"


def test_bash_danger_deny():
    assert evaluate("bash", {"command": "rm -rf /"}) == "deny"


def test_bash_deny_beats_allow():
    """安全底线:命令首词是白名单的 ls,但整串含危险子串 → 仍然 deny。
    (deny 在 allow 之前判——这条红了说明安全顺序被改坏了。)"""
    assert evaluate("bash", {"command": "ls && rm -rf /"}) == "deny"
