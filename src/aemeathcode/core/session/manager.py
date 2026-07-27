from dataclasses import dataclass,field
import uuid
from datetime import datetime

from aemeathcode.core.session.model import Session,ConversationMode,SessionStatus
from aemeathcode.core.task.manager import TaskManager


@dataclass
class SessionRuntime:
    session: Session
    tasks: TaskManager = field(default_factory=TaskManager)
    total_input_tokens :int = 0
    total_output_tokens :int = 0
    total_cache_read :int = 0
    run_messages:dict[str,list[dict]] = field(default_factory=dict)

class SessionManager:
    def __init__(self, store):
        self._store = store
        self._runtimes: dict[str, SessionRuntime] = {}

    def create(self,mode:ConversationMode) -> SessionRuntime:
        session_id = str(uuid.uuid4())
        now = datetime.now()
        session = Session(id=session_id,
                          conversation_mode=mode,
                          title="新建会话",
                          created_at=now,
                          updated_at=now)
        session_runtime = SessionRuntime(session=session)
        self._runtimes[session_id] = session_runtime
        # 故意【不】在这里落盘:空会话(没跑过 run)不该进磁盘/picker。
        # 等第一个 run 开跑(mark_active→_touch→save_meta)才真正落盘,"有内容的才存"。
        return session_runtime

    def get(self,session_id:str) -> SessionRuntime|None:
        return self._runtimes.get(session_id)

    def resume(self,session_id:str) -> SessionRuntime:
        """内存有就直接用;没有就从磁盘 load 回来、拼成 SessionRuntime 放进内存。"""
        runtime = self._runtimes.get(session_id)
        if runtime is not None:
            return runtime
        data = self._store.load_session(session_id)   # 查无此会话会抛 FileNotFoundError
        runtime = SessionRuntime(
            session=data["session"],
            tasks=data["tasks"],
            total_input_tokens=data["tokens"]["total_input_tokens"],
            total_output_tokens=data["tokens"]["total_output_tokens"],
            total_cache_read=data["tokens"]["total_cache_read"],
            run_messages=data["run_messages"],
        )
        self._runtimes[session_id] = runtime
        return runtime

    def _touch(self,runtime:SessionRuntime) -> None:
        # 甲:每次状态变动的唯一汇聚点 —— 更新时间戳 + 落盘 meta,磁盘永远跟内存一致
        runtime.session.updated_at = datetime.now()
        self._store.save_meta(runtime)

    def _set_status(self,session_id:str,status:SessionStatus) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is not None:
            runtime.session.status = status
            self._touch(runtime)

    def set_title(self, session_id, title):
        runtime = self.get(session_id)
        if runtime is not None:
            runtime.session.title = title
            self._touch(runtime)

    def mark_active(self,session_id:str) -> None:
        self._set_status(session_id,SessionStatus.ACTIVE)

    def mark_waiting(self,session_id:str) -> None:
        self._set_status(session_id,SessionStatus.WAITING)

    def mark_closed(self,session_id:str) -> None:
        self._set_status(session_id,SessionStatus.CLOSED)

    def add_run(self,session_id:str,run_id:str) -> None:
        runtime = self.get(session_id)
        if runtime is not None:
            runtime.session.run_ids.append(run_id)
            self._touch(runtime)

    def append_run_messages(self,session_id:str,run_id:str,increment:list[dict])->None:
        runtime = self.get(session_id)
        if runtime is not None:
            runtime.run_messages[run_id] = increment
            self._store.append_run(session_id, run_id, increment)   # 增量追加进 ndjson
            self._touch(runtime)                                    # 顺带落一次 meta(甲)

    def build_history(self,session_id:str)->list[dict]:
        runtime = self.get(session_id)
        history = []
        if runtime is not None:
            for run_id in runtime.session.run_ids:
                history.extend(runtime.run_messages.get(run_id,[]))

        return history

    def add_token(self,session_id:str,
                  input_tokens:int,
                  output_tokens:int,
                  cache_read:int
                  ) -> None:
        runtime = self.get(session_id)
        if runtime is not None:
            runtime.total_input_tokens += input_tokens
            runtime.total_output_tokens += output_tokens
            runtime.total_cache_read += cache_read
            self._touch(runtime)
