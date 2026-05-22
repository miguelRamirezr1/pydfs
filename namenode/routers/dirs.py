from fastapi import APIRouter, Depends, HTTPException, Response, status

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


@router.delete("/{path:path}", status_code=204)
def delete_dir(path: str, owner: str = Depends(get_current_user)):
    path = path.strip("/")
    if not path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ruta inválida")
    result = db.delete_dir(owner, path)
    if result == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Directorio no encontrado")
    if result == "not_empty":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El directorio no está vacío")
    return Response(status_code=204)
