"""
 pdf-pipeline CLI  (extract + clean only)

 USAGE
 =====
 # 1) extract raw artefacts
 pdf-pipeline extract docs/outlook_2025.pdf --out data/extracted

 # 2) clean them into Markdown
 pdf-pipeline clean outlook_2025 \
               --root data/extracted \
               --out  data/cleaned
"""

from __future__ import annotations
import argparse, sys
from pathlib import Path

from .extractor import Extractor            # your full class
from .clean     import clean_markdown       # wrapper around tools/…

# ------------------------------------------------------------------- handlers

def _cmd_extract(args: argparse.Namespace) -> None:
    pdf_path = Path(args.pdf).expanduser()
    out_root = Path(args.out).expanduser()

    Extractor(out_root).extract(pdf_path)
    print("✔ extracted to", out_root / pdf_path.stem)


def _cmd_clean(args: argparse.Namespace) -> None:
    slug = args.slug
    raw_root = Path(args.root).expanduser()
    out_root = Path(args.out).expanduser()

    md = clean_markdown(
        slug,
        extracted_root=raw_root,
        output_filename="organized_cleaned_document.md",
        debug=args.debug,
    )
    print("✔ cleaned Markdown written to", md)

# ------------------------------------------------------------------- arg-parser

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("pdf-pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    # extract
    px = sub.add_parser("extract", help="PDF → raw artifacts")
    px.add_argument("pdf", help="path to PDF file")
    px.add_argument("--out", default="data",
                    help="output root dir (default: data)")
    px.set_defaults(func=_cmd_extract)

    # clean
    pc = sub.add_parser("clean", help="raw artifacts → Markdown")
    pc.add_argument("slug", help="folder name under extracted root")
    pc.add_argument("--root", default="data",
                    help="where the raw artifacts live")
    pc.add_argument("--out",  default="cleaned",
                    help="folder to write Markdown")
    pc.add_argument("--debug", action="store_true", help="verbose skip logs")
    pc.set_defaults(func=_cmd_clean)

    return p

# ------------------------------------------------------------------- entry-point

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        args.func(args)        # dispatch to chosen sub-command
    except Exception as exc:   # bubble up for CI / shell
        parser.error(str(exc))
        sys.exit(1)

if __name__ == "__main__":
    main()
