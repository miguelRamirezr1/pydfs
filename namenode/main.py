from contextlib import asynccontextmanager
from fastapi import FastAPI
from metadata import init_db
from routers import auth as auth_router, datanodes as datanodes_router, dirs as dirs_router, files as files_router
from scheduler import start_heartbeat_monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_heartbeat_monitor()
    yield


app = FastAPI(title="NameNode", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(files_router.router)
app.include_router(dirs_router.router)
app.include_router(datanodes_router.router)
