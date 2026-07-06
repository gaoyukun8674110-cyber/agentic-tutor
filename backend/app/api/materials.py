"""Study material upload and retrieval API."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.materials import SUPPORTED_EXTENSIONS, MaterialService
from app.utils.errors import api_error
from app.utils.upload import max_upload_bytes, read_validated_upload

router = APIRouter(prefix="/api/materials", tags=["materials"], dependencies=[Depends(get_current_user)])


class MaterialSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    material_ids: list[int] | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)


@router.post("/upload", response_model=dict)
async def upload_material(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload one learning material and make it searchable."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_upload_bytes() + 1024 * 1024:
        raise api_error(413, "upload_too_large", f"Upload exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit")

    content = await read_validated_upload(file)
    service = MaterialService(db)
    try:
        material = service.create_pending_material_from_bytes(
            filename=file.filename or "material",
            content=content,
            content_type=file.content_type,
            user_id=current_user.username,
        )
        background_tasks.add_task(service.fill_material_embeddings, int(material["id"]))
        return material
    except ValueError as error:
        raise api_error(400, "invalid_material", str(error)) from error


@router.get("", response_model=dict)
def list_materials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List uploaded learning materials."""
    service = MaterialService(db)
    return {
        "materials": service.list_materials(user_id=current_user.username),
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


@router.post("/search", response_model=dict)
def search_materials(
    request: MaterialSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search uploaded learning materials for Tutor context."""
    service = MaterialService(db)
    chunks: list[dict[str, Any]] = service.search_materials(
        query=request.query,
        user_id=current_user.username,
        material_ids=request.material_ids,
        top_k=request.top_k,
    )
    return {"chunks": chunks, "embedding_mode": service.embedding_mode}
