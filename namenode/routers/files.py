import logging
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status

from auth import get_current_user
import metadata as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


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
