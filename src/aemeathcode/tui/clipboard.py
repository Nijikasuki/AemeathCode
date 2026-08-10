"""把文本送进系统剪贴板。

为什么不能只靠 Textual 的 `copy_to_clipboard`:它走 OSC 52 —— 由程序往终端吐一段
转义序列、请求终端代为写剪贴板。这条路**依赖终端配合**,很多终端默认不开(实测在
WSL + Windows Terminal 下就没生效),而且**失败是静默的**,程序拿不到任何反馈。
上一版因此报了"已复制"却什么都没进剪贴板 —— 假成功比不能用更糟。

所以顺序反过来:优先调用系统自带的剪贴板命令(能拿到退出码 = 能如实报告),
实在没有再退回 OSC 52。
"""
from __future__ import annotations

import shutil
import subprocess


def _utf16_bom(text: str) -> bytes:
    """UTF-16LE **带 BOM**。

    `clip.exe` 按**当前控制台代码页**解读 stdin —— 中文 Windows 下是 CP936,
    直接喂 UTF-8 会得到"浣犲ソ"这种经典乱码。带 BOM 的 UTF-16LE 能让它认出编码。

    两个踩过的坑:
      * **BOM 不能省。**只转 UTF-16LE 不加 BOM 照样全乱,就差那两个字节。
      * 别用 CP936 —— 中文是能对,但 GBK 之外的字符(`✧`、emoji)会直接丢。
    """
    return b"\xff\xfe" + text.encode("utf-16-le")


def _utf8(text: str) -> bytes:
    return text.encode("utf-8")


# (可执行文件, 命令, 编码器)。按优先级排,第一个存在的胜出。
HELPERS = (
    ("clip.exe", ["clip.exe"], _utf16_bom),          # WSL 下唯一真正到达 Windows 剪贴板的路子
    ("wl-copy", ["wl-copy"], _utf8),
    ("pbcopy", ["pbcopy"], _utf8),
    ("xclip", ["xclip", "-selection", "clipboard"], _utf8),
    ("xsel", ["xsel", "--clipboard", "--input"], _utf8),
)


def helper():
    for exe, cmd, enc in HELPERS:
        if shutil.which(exe):
            return cmd, enc
    return None


def copy(text: str) -> str | None:
    """写剪贴板。成功返回用的命令名,没有可用命令返回 None(调用方去走 OSC 52 兜底)。

    命令存在但执行失败会抛 —— 那属于真错误,不该被当成"没有剪贴板"吞掉。
    """
    found = helper()
    if found is None:
        return None
    cmd, enc = found
    subprocess.run(cmd, input=enc(text), check=True, timeout=5)
    return cmd[0]
