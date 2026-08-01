import logging
logger = logging.getLogger(__name__)

from pydantic import BaseModel


class EventBus:
    def __init__(self):
        self._subscribers = []


    def subscribe(self,handler):
        self._subscribers.append(handler)

    async def publish(self,event:BaseModel):
        for subscriber in self._subscribers:
            try:
                await subscriber(event)
            except Exception:  # 注意:只抓 Exception,放 CancelledError 过
                logger.exception("订阅者处理事件失败: %s", getattr(subscriber, "__name__", subscriber))
