from contextlib import asynccontextmanager
from fastapi import FastAPI
from metadata import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NameNode", lifespan=lifespan)
