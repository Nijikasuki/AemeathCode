from pydantic import BaseModel


class Task(BaseModel):
    id:int
    content:str
    status:str

    def to_line(self) -> str:
        """给 LLM 看的一行文本:[#1] pending · 写测试"""
        return f"[#{self.id}] {self.status} · {self.content}"