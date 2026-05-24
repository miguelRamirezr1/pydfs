from contextlib import asynccontextmanager
from fastapi import FastAPI
from heartbeat import start as start_heartbeat
from routers import blocks as blocks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_heartbeat()
    yield


app = FastAPI(title="DataNode", lifespan=lifespan)
app.include_router(blocks_router.router)
