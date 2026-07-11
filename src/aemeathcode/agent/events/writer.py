import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from aemeathcode.agent.events.bus import EventBus
from aemeathcode.agent.events.models import RunStartedEvent


class FileWriter:
    def __init__(self, file_path:Path):
        self.file_path = file_path

    async def write(self, event:BaseModel):
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")





if "__main__" == __name__:
    async def test():
        bus = EventBus()
        run_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        writer = FileWriter(Path(f"/home/administrator/cc_learn/AemeathCode/run/events_{run_time}.ndjson"))
        bus.subscribe(writer.write)  # 挂上文件订阅者
        await bus.publish(RunStartedEvent(goal="aaaaa"))

    asyncio.run(test())