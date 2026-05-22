from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
import metadata as db

router = APIRouter(prefix="/dirs", tags=["dirs"])


@router.post("/{path:path}", status_code=201)
def create_dir(path: str, owner: str = Depends(get_current_user)):
    path = path.strip("/")
    if not path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ruta inválida")
    ok = db.create_dir(owner, path)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El directorio ya existe")
    return {"path": path}
