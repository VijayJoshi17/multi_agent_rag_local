"""Tabular datasets for the Data Analyst agent."""

import io
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import NotFoundError, UnsupportedFileError
from app.db.models import Dataset
from app.services import parsing


def _read_frame(ext: str, data: bytes | Path, nrows: int | None = None) -> pd.DataFrame:
    src = io.BytesIO(data) if isinstance(data, bytes) else data
    if ext == ".csv":
        return pd.read_csv(src, nrows=nrows)
    return pd.read_excel(src, nrows=nrows)


class DatasetService:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[AsyncSession]):
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.dir = settings.datasets_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, ds: Dataset) -> Path:
        return self.dir / ds.stored_name

    async def create(self, filename: str, data: bytes) -> Dataset:
        ext = parsing.sniff(filename, data)
        if ext not in parsing.DATASET_EXTS:
            raise UnsupportedFileError("Datasets must be .csv or .xlsx")
        try:
            df = await run_in_threadpool(_read_frame, ext, data)
        except Exception as e:  # noqa: BLE001
            raise UnsupportedFileError(f"Could not parse {filename}: {e}") from e

        ds = Dataset(
            filename=filename, stored_name="", size_bytes=len(data), row_count=len(df),
            columns=[{"name": str(c), "dtype": str(t)} for c, t in df.dtypes.items()],
        )
        async with self.sessionmaker() as s:
            s.add(ds)
            await s.flush()
            ds.stored_name = f"{ds.id}{ext}"
            await run_in_threadpool(self.path(ds).write_bytes, data)
            await s.commit()
        return ds

    async def get(self, dataset_id: str | None) -> Dataset:
        """Fetch by id, or the most recent dataset when id is None."""
        async with self.sessionmaker() as s:
            if dataset_id:
                ds = await s.get(Dataset, dataset_id)
            else:
                ds = await s.scalar(select(Dataset).order_by(Dataset.created_at.desc()).limit(1))
        if ds is None:
            raise NotFoundError("Dataset not found. Upload a CSV or Excel file first.")
        return ds

    async def preview(self, ds: Dataset, rows: int = 20) -> tuple[list[str], list[list[object]]]:
        df = await run_in_threadpool(
            _read_frame, parsing.extension(ds.stored_name), self.path(ds), rows
        )
        df = df.astype(object).where(df.notna(), None)
        return [str(c) for c in df.columns], df.values.tolist()

    async def sample(self, ds: Dataset, rows: int = 5) -> str:
        df = await run_in_threadpool(
            _read_frame, parsing.extension(ds.stored_name), self.path(ds), rows
        )
        return df.to_markdown(index=False)

    async def delete(self, ds: Dataset) -> None:
        self.path(ds).unlink(missing_ok=True)
