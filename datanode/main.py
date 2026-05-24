from contextlib import asynccontextmanager
from fastapi import FastAPI
from heartbeat import start as start_heartbeat


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_heartbeat()
    yield


app = FastAPI(title="DataNode", lifespan=lifespan)
