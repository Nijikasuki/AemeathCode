import asyncio
from pathlib import Path
from aemeathcode.core.trace.record import TraceRecord

class TraceWriter:
    def __init__(self, file_path:Path):
        self.file_path = file_path
        self._queue = asyncio.Queue()
        self._task = None

    def emit(self, record: TraceRecord):
        self._queue.put_nowait(record)

    def start(self):
        self._task = asyncio.create_task(self._drain())

    async def stop(self):
        await self._queue.join()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _drain(self):
        with open(self.file_path, "a", encoding="utf-8") as f:
            while True:
                record = await self._queue.get()
                f.write(record.model_dump_json() + "\n")
                f.flush()
                self._queue.task_done()
