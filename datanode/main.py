import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from heartbeat import start as start_heartbeat
from routers import blocks as blocks_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NODE_ID = os.getenv("NODE_ID", "dn0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DataNode %s arrancando", NODE_ID)
    start_heartbeat()
    logger.info("DataNode %s listo", NODE_ID)
    yield
    logger.info("DataNode %s apagándose", NODE_ID)


app = FastAPI(title="DataNode", lifespan=lifespan)
app.include_router(blocks_router.router)
