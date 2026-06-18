"""
Wrapper around tools/postprocessing_document.py so the function becomes
importable as pdf_pipeline.clean.clean_markdown().
"""

from pathlib import Path
import importlib.util
import runpy


# ---------- dynamic import so we don't duplicate code ---------------
_spec = importlib.util.spec_from_file_location(
    "postprocess",         # arbitrary name
    "src/pdf_pipeline/postprocessing_document.py",
)
_post = importlib.util.module_from_spec(_spec)        # type: ignore[arg-type]
_spec.loader.exec_module(_post)                       # type: ignore[union-attr]
# now _post.organize_and_clean_by_section is live


def clean_markdown(
    slug: str,
    extracted_root: str | Path = "data",
    output_filename: str = "organized_cleaned_document.md",
    debug: bool = False,
) -> Path:
    """
    Public helper used by CLI:

        pdf-pipeline clean <slug>
    """
    _post.organize_and_clean_by_section(
        extracted_base_dir=str(extracted_root),
        pdf_name=slug,
        output_filename=output_filename,
        debug=debug,
    )
    return Path(extracted_root) / slug / output_filename
