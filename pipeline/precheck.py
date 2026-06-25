import hashlib
from pathlib import Path

from PyPDF2 import PdfReader
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# ─── config ───────────────────────────────────────────────────────────────
load_dotenv()
IRIS_CONN_STR = os.getenv("IRIS_CONN_STR")
if not IRIS_CONN_STR:
    raise RuntimeError("IRIS_CONN_STR not set in .env")

engine = create_engine(IRIS_CONN_STR)


def ensure_meta_table() -> None:
    """Create the small metadata table if it doesn't already exist."""
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS Embedding.DocumentMeta (
          slug        VARCHAR(100) PRIMARY KEY,
          file_hash   VARCHAR(64),
          size_bytes  INT,
          page_count  INT,
          uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """))


def check_duplicate(pdf_path: Path, slug: str):
    """
    Fast‐path duplicate check.
    Returns (is_duplicate: bool, uploaded_at: datetime|None, file_hash, size_bytes, page_count)
    """
    # 1) size
    size_bytes = pdf_path.stat().st_size

    # 2) page count
    page_count = len(PdfReader(str(pdf_path)).pages)

    # 3) streaming SHA-256
    hasher = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()

    # 4) lookup
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT uploaded_at
              FROM Embedding.DocumentMeta
             WHERE file_hash = :h
                OR slug      = :slug
        """), {"h": file_hash, "slug": slug}).first()

    if row:
        return True, row.uploaded_at, file_hash, size_bytes, page_count
    else:
        return False, None, file_hash, size_bytes, page_count


def record_metadata(slug: str, file_hash: str, size_bytes: int, page_count: int):
    """After a successful load, insert the metadata."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO Embedding.DocumentMeta
              (slug, file_hash, size_bytes, page_count)
            VALUES (:slug, :h, :size, :pages)
        """), {
            "slug": slug,
            "h": file_hash,
            "size": size_bytes,
            "pages": page_count
        })
