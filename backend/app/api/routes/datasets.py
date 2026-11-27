from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session, limiter, read_upload
from app.container import Container
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.models import Dataset
from app.schemas.api import DatasetOut, DatasetPreview

router = APIRouter(tags=["datasets"])


@router.post("/datasets", response_model=DatasetOut, status_code=201)
@limiter.limit(lambda: get_settings().RATE_LIMIT_UPLOAD)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(..., description="CSV or XLSX"),
    c: Container = Depends(get_container),
) -> Dataset:
    data = await read_upload(file, c.settings.MAX_UPLOAD_MB * 1024 * 1024)
    return await c.datasets.create(file.filename or "dataset.csv", data)


@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(s: AsyncSession = Depends(get_session)) -> list[Dataset]:
    return list(await s.scalars(select(Dataset).order_by(Dataset.created_at.desc())))


@router.get("/datasets/{dataset_id}/preview", response_model=DatasetPreview)
async def preview_dataset(
    dataset_id: str, rows: int = 20, c: Container = Depends(get_container)
) -> DatasetPreview:
    ds = await c.datasets.get(dataset_id)
    columns, data = await c.datasets.preview(ds, rows=max(1, min(rows, 100)))
    return DatasetPreview(columns=columns, rows=data)


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str,
    s: AsyncSession = Depends(get_session),
    c: Container = Depends(get_container),
) -> Response:
    ds = await s.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("Dataset not found")
    await c.datasets.delete(ds)
    await s.delete(ds)
    await s.commit()
    return Response(status_code=204)
