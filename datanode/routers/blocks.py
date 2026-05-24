import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

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

    if replica_host and replica_port:
        url = f"http://{replica_host}:{replica_port}/blocks/{block_id}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, content=data, timeout=30)
                resp.raise_for_status()
        except Exception as exc:
            (BLOCKS_DIR / block_id).unlink(missing_ok=True)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"replicación fallida: {exc}")

    return {"status": "ok", "block_id": block_id}


@router.get("/{block_id}")
def get_block(block_id: str):
    path = BLOCKS_DIR / block_id
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bloque no encontrado")
    return FileResponse(path, media_type="application/octet-stream")
