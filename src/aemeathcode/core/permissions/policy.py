from typing import Literal
from dataclasses import dataclass, field


Decision = Literal["allow","deny","ask"]

@dataclass
class ToolPolicy:
    default: Decision                    # 都不命中时返回它
    deny: list[str] = field(default_factory=list) # 子串黑名单(整串匹配)
    allow: set[str] = field(default_factory=set) # 首词白名单

SAFE_CMDS = {
    "pwd",
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "find",
    "tree",
}

DANGER = [
    "rm -rf /", "rm -fr /", "rm -rf /*", "rm -rf ~",   # 删根/家目录
    "mkfs",                        # 格式化文件系统
    "dd of=/dev/",                 # 直写裸设备
    "> /dev/sda", "> /dev/sd",     # 覆盖磁盘
    ":(){", ":|:&",                # fork 炸弹
    "chmod -R 777 /", "chown -R",  # 权限灾难
    "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",  # 关机/重启
]

TOOL_POLICIES = {
    "read_file": ToolPolicy(default="allow"),
    "list_dir": ToolPolicy(default="allow"),
    "note_save": ToolPolicy(default="allow"),
    "task_create": ToolPolicy(default="allow"),
    "task_get": ToolPolicy(default="allow"),
    "task_list": ToolPolicy(default="allow"),
    "task_update": ToolPolicy(default="allow"),
    "use_skill": ToolPolicy(default="allow"),   # 只读加载本地 md 指令,无副作用
    "write_file": ToolPolicy(default="ask"),
    "bash": ToolPolicy(default="ask", deny=DANGER, allow=SAFE_CMDS),
}


def evaluate(tool,params)->Decision:
    policy = TOOL_POLICIES.get(tool)
    if policy is None:  # 未知工具兜底(你正好要补的那个)
        return "ask"
    command = params.get("command", "")  # 非 bash 工具没这参数 → 空串,下面两个循环自然空转
    for p in policy.deny:
        if p in command: return "deny"
    parts = command.split()
    first = parts[0] if parts else ""
    if first in policy.allow: return "allow"
    return policy.default