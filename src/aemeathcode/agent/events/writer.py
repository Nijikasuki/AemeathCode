from pathlib import Path

from pydantic import BaseModel


class FileWriter:
    def __init__(self, file_path:Path):
        self.file_path = file_path

    async def write(self, event:BaseModel):
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
