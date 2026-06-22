# extractor.py
"""
PDF extractor: pulls text, images, tables & rich metadata from a single PDF
using the `unstructured` framework.  Output tree:

    extracted_pdfs/<slug>/
      text/                ← .txt files for every Text/Title block
      images/              ← PNG/JPGs for Images and Table snapshots
      tables/              ← .txt + .html for each table
      combined_text.txt    ← all text concatenated
      document_metadata.json  ← master metadata (stats + per-element records)

Run from CLI:

    python extractor.py my_report.pdf
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _locate_tesseract() -> str | None:
    """Find the Tesseract binary without a hard-coded, machine-specific path.

    Priority: TESSERACT_CMD env var -> system PATH -> common install locations.
    Returns None if not found (extraction with the default "fast" path still
    works; only OCR / hi_res needs Tesseract).
    """
    explicit = os.environ.get("TESSERACT_CMD")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ):
        if Path(candidate).exists():
            return candidate
    return None


_TESSERACT_EXE = _locate_tesseract()
if _TESSERACT_EXE:
    # Point both pytesseract and unstructured's vendored copy at the binary,
    # and make sure its directory is on PATH for the current process.
    os.environ["PATH"] = os.path.dirname(_TESSERACT_EXE) + os.pathsep + os.environ.get("PATH", "")
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE
    import unstructured_pytesseract
    unstructured_pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE

from unstructured.documents.elements import (  # noqa: E402
    Element,
    Image,
    ListItem,
    NarrativeText,
    Table,
    Text,
    Title,
)
from unstructured.partition.pdf import partition_pdf

################################################################################
# ─────────────────────────────────── helpers ──────────────────────────────────
################################################################################
class _DirBundle(Tuple[Path, Path, Path, Path]):
    """base, text/, images/, tables/"""


class _Counters(dict[str, int]):
    """
    Tiny mutable counter object with default zeros.

    Usage:
        stats = _Counters()
        stats.bump("images")
    """

    def __init__(self) -> None:
        super().__init__(text=0, titles=0, images=0, tables=0)

    def bump(self, key: str) -> None:  # noqa: D401
        self[key] = self.get(key, 0) + 1


################################################################################
# ────────────────────────────────── main class ────────────────────────────────
################################################################################

class Extractor:
    """Built around unstructured.io, hides all path juggling"""

    def __init__(self, output_root: str | os.PathLike = "data") -> None:
        self.root = Path(output_root)

    # --------------------------------------------------------------------- public

    def extract(
        self,
        pdf_file: str | os.PathLike,
        *,
        strategy: str = "hi_res",
        keep_images: bool = True,
        keep_tables: bool = True,
    ) -> Dict[str, int]:
        """
        Parameters
        ----------
        pdf_file
            Path to the source PDF.
        strategy
            unstructured's layout strategy (``"hi_res"`` recommended).
        keep_images, keep_tables
            Toggle image / table extraction (saves time if False).

        Returns
        -------
        dict
            Basic statistics (text blocks, titles, images, tables).
        """
        slug = Path(pdf_file).stem
        base_dir, txt_dir, img_dir, tbl_dir = self._mk_dirs(slug)

        # --- call unstructured ------------------------------------------------
        elements = self._run_partition(
            pdf_file,
            strategy=strategy,
            extract_images=keep_images,
            extract_tables=keep_tables,
            images_dir=img_dir,     # use the unpacked variable
        )

        # --- serialize every element -----------------------------------------
        meta, stats = self._serialize(
            elements, 
            Path(pdf_file),
            (base_dir, txt_dir, img_dir, tbl_dir),
        )

        # --- final metadata file ---------------------------------------------
        self._write_outputs(meta, stats, base_dir)
        return stats


    # 1. dirs -------------------------------------------------------------

    @staticmethod
    def _mk_dirs(slug: str) -> _DirBundle:
        base = Path("data") / slug
        txt  = base / "text"
        img  = base / "images"
        tbl  = base / "tables"
        for p in (base, txt, img, tbl):
            p.mkdir(parents=True, exist_ok=True)
        return _DirBundle((base, txt, img, tbl))

    # 2. unstructured call -----------------------------------------------

    @staticmethod
    def _run_partition(
        pdf_path: str | os.PathLike,
        *,
        strategy: str,
        extract_images: bool,
        extract_tables: bool,
        images_dir: Path,
    ) -> List[Element]:
        """
        Call `partition_pdf` with the right set of `extract_image_block_types`.

        We add "Image" when `keep_images` is True, and "Table" when
        `keep_tables` is True so that table snapshots are rendered to PNG.
        """
        img_types = [] 
        if extract_images is True: 
            img_types.append("Image")
        if extract_tables is True:
            img_types.append("Table")
        tbl_flag = extract_tables

        return partition_pdf(
            filename=str(pdf_path),
            strategy=strategy,
            extract_image_block_types=img_types,
            extract_image_block_output_dir=str(images_dir),
            infer_table_structure=tbl_flag,
        )

    # 3. iterate elements -------------------------------------------------

    def _serialize(
        self,
        elements: List[Element],
        src_path: Path,
        dirs: _DirBundle,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Walk every element, write its payload to disk, accumulate metadata.
        """
        base, txt_dir, _, tbl_dir = dirs
        meta_records: List[Dict[str, Any]] = []
        stats = _Counters()
        combined: List[str] = []

        for idx, el in enumerate(elements):
            # static metadata (element_index, type, page_number, etc.)
            rec = self._meta_stub(el, idx, src_path)

            # ---------- TABLE -------------------------------------------------
            if isinstance(el, Table):
                # ---------- write plain-text representation ----------
                txt_path = tbl_dir / f"table_{idx}.txt"
                txt_path.write_text(el.text, encoding="utf-8")
                rec["content_path"] = str(txt_path)
                # ---------- keep HTML if supplied ----------
                html = getattr(el.metadata, "text_as_html", None)
                if html:
                    html_path = tbl_dir / f"table_{idx}.html"
                    html_path.write_text(html, encoding="utf-8")
                    rec["html_path"] = str(html_path)

                rec["image_path"] = el.metadata.image_path   
                stats.bump("tables")

            # ---------- IMAGE ------------------------------------------------
            elif isinstance(el, Image):
                rec["image_path"] = el.metadata.image_path
                stats.bump("images")
            
            # ---------- TITLE -------------------------------------------------
            elif isinstance(el, Title):
                path = txt_dir / f"{el.__class__.__name__.lower()}_{idx}.txt"
                path.write_text(el.text, encoding="utf-8")
                rec["content_path"] = str(path)
                combined.append(el.text.strip())
                stats.bump("titles")

            # ---------- GENERIC TEXT (NarrativeText, ListItem, etc.) ----------
            elif isinstance(el, Text):        
                path = txt_dir / f"{el.__class__.__name__.lower()}_{idx}.txt"
                path.write_text(el.text, encoding="utf-8")
                rec["content_path"] = str(path)
                combined.append(el.text.strip())
                stats.bump("text")

            # ---------- record finished ---------------------------------------
            meta_records.append(rec)

        # single combined text file
        (base / "combined_text.txt").write_text("\n\n".join(combined), encoding="utf-8")
        return meta_records, dict(stats)

    # 4. write JSON metadata ---------------------------------------------

    @staticmethod
    def _write_outputs(
        meta: List[Dict[str, Any]],
        stats: Dict[str, int],
        base_dir: Path,
    ) -> None:
        """Dump final `document_metadata.json` with stats + per-element records."""
        payload = {
            "filename": base_dir.name + ".pdf",
            "extraction_date": datetime.utcnow().isoformat(),
            "statistics": stats,
            "elements_metadata": meta,
        }
        (base_dir / "document_metadata.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # --------------------------------------------------------------------- utilities

    @staticmethod
    def _meta_stub(el: Element, idx: int, src: Path) -> Dict[str, Any]:
        """
        Common metadata extracted from every Element object.
        """
        m: Dict[str, Any] = {
            "element_index": idx,
            "element_type": el.__class__.__name__,
            "filename": src.name,
        }
        if hasattr(el, "metadata"):
            md = el.metadata
            for fld in (
                "page_number",
                "section",
                "text_as_html",
                "image_path",
                "detection_class_prob",
            ):
                if hasattr(md, fld) and (v := getattr(md, fld)):
                    m[fld] = v
            if coords := getattr(md, "coordinates", None):
                m["coordinates"] = {
                    "points": coords.points,
                    "system": str(coords.system) if hasattr(coords, "system") else None,
                }
        return m


#######################################################################################
# CLI wrapper
#######################################################################################

def _cli() -> None:
    """Lightweight argparse wrapper so you can run the file directly."""
    import argparse

    p = argparse.ArgumentParser("pdf-extract-alt")
    p.add_argument("pdf", help="Path to PDF")
    p.add_argument("--no-images", action="store_true", help="skip image extraction")
    p.add_argument("--no-tables", action="store_true", help="skip table extraction")
    p.add_argument("--out", default="extracted_pdfs", help="output root directory")
    args = p.parse_args()

    extractor = Extractor(args.out)
    stats = extractor.extract(
        args.pdf,
        keep_images=not args.no_images,
        keep_tables=not args.no_tables,
    )
    print("✔ extraction complete:", stats)


if __name__ == "__main__":
    _cli()
