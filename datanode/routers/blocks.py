import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BLOCKS_DIR = Path(os.getenv("BLOCKS_DIR", "/app/blocks"))
BLOCKS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.put("/{block_id}", status_code=200)
async def put_block(
    block_id: str,
    request: Request,
    replica_host: Optional[str] = None,
    replica_port: Optional[int] = None,
):
    data = await request.body()
    (BLOCKS_DIR / block_id).write_bytes(data)
    logger.info("bloque recibido: %s (%d bytes)", block_id, len(data))

    if replica_host and replica_port:
        url = f"http://{replica_host}:{replica_port}/blocks/{block_id}"
        logger.info("replicando %s → %s:%s", block_id, replica_host, replica_port)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, content=data, timeout=30)
                resp.raise_for_status()
            logger.info("replicación completada: %s", block_id)
        except Exception as exc:
            (BLOCKS_DIR / block_id).unlink(missing_ok=True)
            logger.error("replicación fallida para %s: %s", block_id, exc)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"replicación fallida: {exc}")

    return {"status": "ok", "block_id": block_id}


@router.get("/{block_id}")
def get_block(block_id: str):
    path = BLOCKS_DIR / block_id
    if not path.exists():
        logger.warning("bloque no encontrado: %s", block_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bloque no encontrado")
    logger.info("sirviendo bloque: %s", block_id)
    return FileResponse(path, media_type="application/octet-stream")


@router.delete("/{block_id}", status_code=204)
def delete_block(block_id: str):
    (BLOCKS_DIR / block_id).unlink(missing_ok=True)
    logger.info("bloque eliminado: %s", block_id)
    return Response(status_code=204)


class ReplicateRequest(BaseModel):
    target_host: str
    target_port: int


@router.post("/{block_id}/replicate", status_code=200)
async def replicate_block(block_id: str, body: ReplicateRequest):
    path = BLOCKS_DIR / block_id
    if not path.exists():
        logger.warning("re-replicación solicitada pero bloque no encontrado: %s", block_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bloque no encontrado")

    data = path.read_bytes()
    url = f"http://{body.target_host}:{body.target_port}/blocks/{block_id}"
    logger.info("re-replicando %s → %s:%s", block_id, body.target_host, body.target_port)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, content=data, timeout=30)
            resp.raise_for_status()
        logger.info("re-replicación completada: %s", block_id)
    except Exception as exc:
        logger.error("re-replicación fallida para %s: %s", block_id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"replicación fallida: {exc}")

    return {"status": "ok", "block_id": block_id}
