import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import metadata as db

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "15"))

router = APIRouter(prefix="/datanodes", tags=["cluster"])


class RegisterRequest(BaseModel):
    node_id: str
    host: str
    port: int
    free_bytes: int = 0


class HeartbeatRequest(BaseModel):
    node_id: str
    free_bytes: int


@router.post("/register", status_code=200)
def register(body: RegisterRequest):
    db.register_datanode(body.node_id, body.host, body.port, body.free_bytes)
    logger.info("DataNode registrado: %s (%s:%s, free=%d bytes)", body.node_id, body.host, body.port, body.free_bytes)
    return {"status": "registered", "node_id": body.node_id}


@router.post("/heartbeat", status_code=200)
def heartbeat(body: HeartbeatRequest):
    if not db.update_heartbeat(body.node_id, body.free_bytes):
        raise HTTPException(status_code=404, detail="DataNode not found")
    return {"status": "ok", "node_id": body.node_id}


@router.get("/status", status_code=200)
def status():
    return db.get_all_datanodes(HEARTBEAT_TIMEOUT)
