import logging
from pydantic import BaseModel


logger = logging.getLogger(__name__)

class EventLogger:
    async def handle(self, event: BaseModel) -> None:
        logger.info("event: %s",event.model_dump())

