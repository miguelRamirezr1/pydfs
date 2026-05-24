import os
from pathlib import Path

from fastapi import APIRouter, Request

BLOCKS_DIR = Path(os.getenv("BLOCKS_DIR", "/app/blocks"))
BLOCKS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.put("/{block_id}", status_code=200)
async def put_block(block_id: str, request: Request):
    data = await request.body()
    (BLOCKS_DIR / block_id).write_bytes(data)
    return {"status": "ok", "block_id": block_id}
