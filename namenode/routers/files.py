from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
import metadata as db

router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
def list_files(directory: Optional[str] = None, owner: str = Depends(get_current_user)):
    return db.list_files(owner, directory)


@router.get("/{path:path}")
def get_file(path: str, owner: str = Depends(get_current_user)):
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
