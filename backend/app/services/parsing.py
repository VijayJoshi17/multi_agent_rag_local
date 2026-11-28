"""Safe file-type detection and text extraction. Everything is parsed from bytes in memory —
uploads are never extracted onto the filesystem, which rules out zip-slip by construction."""

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.errors import PayloadTooLargeError, UnsupportedFileError

DOCUMENT_EXTS = {".txt", ".md", ".pdf", ".docx", ".pptx"}
DATASET_EXTS = {".csv", ".xlsx"}
ARCHIVE_EXTS = {".zip"}

_ZIP_BASED = {".docx", ".pptx", ".xlsx", ".zip"}


@dataclass(slots=True)
class PageText:
    text: str
    page: int | None = None


@dataclass(slots=True)
class FilePayload:
    filename: str
    ext: str
    data: bytes


def extension(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def sniff(filename: str, data: bytes) -> str:
    """Validate that the bytes match the claimed extension. Returns the extension."""
    ext = extension(filename)
    if ext not in DOCUMENT_EXTS | DATASET_EXTS | ARCHIVE_EXTS:
        raise UnsupportedFileError(f"Unsupported file type '{ext or filename}'")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise UnsupportedFileError(f"{filename} is not a valid PDF")
    if ext in _ZIP_BASED and not data.startswith(b"PK"):
        raise UnsupportedFileError(f"{filename} is not a valid {ext} file")
    if ext in {".txt", ".md", ".csv"}:
        try:
            data[:65536].decode("utf-8")
        except UnicodeDecodeError:
            # Accept a truncated multibyte sequence at the cut boundary.
            try:
                data[:65532].decode("utf-8")
            except UnicodeDecodeError as e:
                raise UnsupportedFileError(f"{filename} is not UTF-8 text") from e
    return ext


def expand_zip(
    filename: str, data: bytes, *, max_members: int, max_total_bytes: int
) -> tuple[list[FilePayload], list[str]]:
    """Read supported documents out of a zip archive with bomb/traversal protection."""
    accepted: list[FilePayload] = []
    skipped: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise UnsupportedFileError(f"{filename} is not a valid zip archive") from e

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_members:
            raise PayloadTooLargeError(f"Archive has {len(infos)} files (max {max_members})")
        if sum(i.file_size for i in infos) > max_total_bytes:
            raise PayloadTooLargeError("Archive is too large when uncompressed")

        for info in infos:
            name = info.filename
            parts = PurePosixPath(name.replace("\\", "/")).parts
            if name.startswith(("/", "\\")) or ".." in parts or "__MACOSX" in parts:
                skipped.append(name)
                continue
            ext = extension(name)
            if ext not in DOCUMENT_EXTS:
                skipped.append(name)
                continue
            member = zf.read(info)
            try:
                sniff(name, member)
            except UnsupportedFileError:
                skipped.append(name)
                continue
            accepted.append(FilePayload(f"{filename}/{name}", ext, member))
    return accepted, skipped


def extract_text(ext: str, data: bytes) -> list[PageText]:
    if ext in {".txt", ".md", ".url"}:  # .url = text already extracted from a web page
        return [PageText(data.decode("utf-8", errors="replace"))]
    if ext == ".pdf":
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        return [
            PageText(page.extract_text() or "", page=i + 1) for i, page in enumerate(reader.pages)
        ]
    if ext == ".docx":
        import docx

        doc = docx.Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return [PageText("\n".join(parts))]
    if ext == ".pptx":
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        pages = []
        for i, slide in enumerate(prs.slides):
            texts = [s.text for s in slide.shapes if getattr(s, "has_text_frame", False) and s.text]
            pages.append(PageText("\n".join(texts), page=i + 1))
        return pages
    raise UnsupportedFileError(f"Cannot extract text from {ext}")
