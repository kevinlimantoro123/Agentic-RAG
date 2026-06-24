"""
Extractor sidecar for the RAG2026 IRIS production.

Runs the heavy PDF pipeline (unstructured + OCR -> clean -> chunk) OUT OF PROCESS,
so torch/unstructured can never crash the IRIS kernel. IRIS's PrepareOperation
business operation calls POST /prepare; this service runs extractor -> cleaner ->
chunker and returns the path to the generated chunks.json (which LoadOperation
then loads into Embedding.Clinical).

Run it (from anywhere — it re-roots itself to the repo):

    <repo>/.venv/Scripts/python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800

Strategy:
    SIDECAR_STRATEGY=hi_res  (default) needs Tesseract + Poppler; best for scanned PDFs.
    SIDECAR_STRATEGY=fast    no OCR; fine for digital/text PDFs and quick smoke tests.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Optional

# pipeline/extractor.py and chunker.py resolve paths relative to ./data, so we
# pin the working directory to the repo root (parent of this sidecar/ folder)
# no matter where uvicorn was launched from.
REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline.extractor import Extractor
from pipeline.cleaner import organize_and_clean_by_section
from pipeline.chunker import main as chunk_markdown

app = FastAPI(title="RAG2026 Extractor Sidecar")
DEFAULT_STRATEGY = os.environ.get("SIDECAR_STRATEGY", "fast")

class PrepareIn(BaseModel):
    slug: str
    pdf_path: str
    work_dir: Optional[str] = None
    strategy: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "repo_root": str(REPO_ROOT), "default_strategy": DEFAULT_STRATEGY}


@app.post("/prepare")
def prepare(req: PrepareIn):
    slug = req.slug
    strategy = req.strategy or DEFAULT_STRATEGY

    pdf_path = Path(req.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=400, detail=f"PDF not found at: {pdf_path}")
    if pdf_path.stem != slug:
        # extractor derives the output dir from the filename stem; they must match.
        raise HTTPException(
            status_code=400,
            detail=f"PDF filename stem '{pdf_path.stem}' must equal slug '{slug}'. Rename the file to {slug}.pdf.",
        )

    try:
        # All three steps write under ./data/<slug>/ (relative to REPO_ROOT).
        extractor = Extractor(output_root="data")
        stats = extractor.extract(str(pdf_path), strategy=strategy)

        organize_and_clean_by_section("data", slug)
        chunk_markdown(slug)

        chunks_path = (REPO_ROOT / "data" / slug / "chunks.json").resolve()
        if not chunks_path.exists():
            raise HTTPException(status_code=500, detail=f"chunking produced no file at {chunks_path}")

        return {"chunks_path": str(chunks_path), "stats": stats}
    except HTTPException:
        raise
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)  # surface the full traceback in sidecar.log
        raise HTTPException(status_code=500, detail=tb)
