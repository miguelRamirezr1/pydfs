from fastapi import APIRouter
from pydantic import BaseModel

import metadata as db

router = APIRouter(prefix="/datanodes", tags=["cluster"])


class RegisterRequest(BaseModel):
    node_id: str
    host: str
    port: int
    free_bytes: int = 0


@router.post("/register", status_code=200)
def register(body: RegisterRequest):
    db.register_datanode(body.node_id, body.host, body.port, body.free_bytes)
    return {"status": "registered", "node_id": body.node_id}
