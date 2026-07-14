from dataclasses import dataclass,field


@dataclass
class ExecutionContext:
    goal: str
    max_steps: int
    run_id: str
    reason: str|None = None
    status: str = "running"
    step :int = 0
    messages: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.messages:
            self.messages.append({"role": "user", "content": self.goal})

    def add_assistant_message(self,content:list):
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self,tool_result:list):
        self.messages.append({"role": "user", "content": tool_result})

    def mark_success(self):
        self.status = "success"

    def mark_failed(self,reason:str):
        self.status = "error"
        self.reason = reason

    def is_done(self):
        return self.status != "running"