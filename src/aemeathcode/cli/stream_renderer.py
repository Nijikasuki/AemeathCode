# cli/stream_renderer.py
from aemeathcode.cli.render import render

STREAM_TYPES = {"llm.thinking", "llm.token"}

class StreamRenderer:
    """有状态地把事件流打到终端:
       流事件(思考/token)贴着打、前缀只打一次;普通事件独占一行。
       状态 = 记住当前正在打印哪种流。"""
    def __init__(self):
        self._current = None

    def feed(self, event):
        t = event.get("type")
        if t in STREAM_TYPES:
            self._feed_stream(event,t)
        else:
            self._close()
            print(render(event))


    def _feed_stream(self, event:dict,t:str)->None:
        tag = event["run_id"][:8]  # 取前 8 位当短标签
        prefix = f"[{tag}] "
        if self._current != t:
            self._close()
            self._current = t
            if t == "llm.thinking":
                print(f"{prefix}🧠 思考:",end="",flush=True)
            else:
                print(f"{prefix}",end="",flush=True)
        print(event.get("content"),end="",flush=True)

    def _close(self) -> None:
        if self._current is not None:
            print()
            self._current = None