from typing import Optional

from fastapi import APIRouter, Depends

from auth import get_current_user
import metadata as db

router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
def list_files(directory: Optional[str] = None, owner: str = Depends(get_current_user)):
    return db.list_files(owner, directory)
