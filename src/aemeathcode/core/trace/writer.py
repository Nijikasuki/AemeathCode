from pathlib import Path
from aemeathcode.core.trace.record import TraceRecord

class TraceWriter:
    def __init__(self, file_path:Path):
        self.file_path = file_path

    async def write(self, record:TraceRecord):
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

