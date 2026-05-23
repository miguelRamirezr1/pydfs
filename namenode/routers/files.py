import logging
import math
import os
import uuid
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from auth import get_current_user
import metadata as db
from scheduler import next_two_nodes

logger = logging.getLogger(__name__)

BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", "67108864"))
HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "15"))

router = APIRouter(prefix="/files", tags=["files"])


class UploadRequest(BaseModel):
    path: str
    size: int


class BlockConfirm(BaseModel):
    block_id: str
    seq: int
    primary_node_id: str
    replica_node_id: str


class ConfirmRequest(BaseModel):
    path: str
    size: int
    blocks: list[BlockConfirm]


@router.post("/upload")
def upload_plan(req: UploadRequest, owner: str = Depends(get_current_user)):
    path = req.path.strip("/")
    if req.size < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tamaño inválido")
    if db.get_file(owner, path):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe un archivo en esa ruta")

    active = db.get_active_datanodes(HEARTBEAT_TIMEOUT)
    if len(active) < 2:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Se necesitan al menos 2 DataNodes activos")

    num_blocks = max(1, math.ceil(req.size / BLOCK_SIZE))
    file_id = str(uuid.uuid4())

    blocks = []
    for seq in range(num_blocks):
        primary, replica = next_two_nodes(active)
        blocks.append({
            "block_id": str(uuid.uuid4()),
            "seq": seq,
            "primary_node_id": primary["node_id"],
            "primary_url": f"http://{primary['host']}:{primary['port']}",
            "replica_node_id": replica["node_id"],
            "replica_url": f"http://{replica['host']}:{replica['port']}",
        })

    return {"file_id": file_id, "block_size": BLOCK_SIZE, "blocks": blocks}


@router.post("/{file_id}/confirm", status_code=201)
def confirm_upload(file_id: str, req: ConfirmRequest, owner: str = Depends(get_current_user)):
    path = req.path.strip("/")
    ok = db.create_file(file_id, owner, path, req.size)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El archivo ya fue confirmado o la ruta ya existe")

    for b in req.blocks:
        db.create_block(b.block_id, file_id, b.seq, b.primary_node_id)
        db.create_block(b.block_id, file_id, b.seq, b.replica_node_id)

    return {"ok": True, "file_id": file_id}


@router.get("")
def list_files(directory: Optional[str] = None, owner: str = Depends(get_current_user)):
    return db.list_files(owner, directory)


@router.get("/{path:path}")
def get_file(path: str, owner: str = Depends(get_current_user)):
    path = path.strip("/")
    f = db.get_file(owner, path)
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    return {
        "file_id": f["file_id"],
        "path": f["path"],
        "size": f["size"],
        "created_at": f["created_at"],
        "blocks": db.get_file_blocks(f["file_id"]),
    }


@router.delete("/{path:path}", status_code=204)
def delete_file(path: str, owner: str = Depends(get_current_user)):
    path = path.strip("/")
    blocks = db.delete_file(owner, path)
    if blocks is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado")
    seen = set()
    for b in blocks:
        key = (b["block_id"], b["host"], b["port"])
        if key in seen:
            continue
        seen.add(key)
        url = f"http://{b['host']}:{b['port']}/blocks/{b['block_id']}"
        try:
            requests.delete(url, timeout=5)
        except Exception as exc:
            logger.warning("No se pudo notificar borrado a DataNode %s: %s", url, exc)
    return Response(status_code=204)
