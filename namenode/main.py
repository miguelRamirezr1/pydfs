from contextlib import asynccontextmanager
from fastapi import FastAPI
from metadata import init_db
from routers import auth as auth_router, files as files_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NameNode", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(files_router.router)
