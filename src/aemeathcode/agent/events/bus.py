import asyncio

from pydantic import BaseModel


class EventBus:
    def __init__(self):
        self._subscribers = []


    def subscribe(self,handler):
        self._subscribers.append(handler)

    async def publish(self,event:BaseModel):
        for subscriber in self._subscribers:
            await subscriber(event)




if __name__ == "__main__":
    async def test(event):
        print(event)


    async def test1(event):
        print(f"test1{event}")


    async def main():
        event_bus = EventBus()

        event_bus.subscribe(test)
        event_bus.subscribe(test1)

        await event_bus.publish("test")


    asyncio.run(main())