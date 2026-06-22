# ── chunk_markdown_langchain.py ────────────────────────────────────────
"""
Reads a cleaned Markdown file, splits it by heading hierarchy,
then splits those sections into overlapping chunks (~750 words each),
ensures each chunk is ≤ 512 GPT tokens, and saves as a JSON array.
No OpenAI key is needed (token counting uses `tiktoken`).
"""

import json, uuid, re, sys
from pathlib import Path
from tqdm import tqdm  # tqdm provides a progress bar during iteration
import tiktoken
from dateutil import parser as dtparse   # pip install python-dateutil
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

# ---------------------------- CONFIG ------------------------------------

# # Input path to the cleaned Markdown file
# MD_PATH  = Path("C:/Users/Siyer/OneDrive - InterSystems Corporation/Documents/GitHub/agentic-AI/data/Sample_Notes/organized_cleaned_document.md")

# # Output path (JSON array instead of JSONL)
# OUT_PATH = MD_PATH.with_name("chunks.json")

# Markdown heading levels used to split the document
HEADER_LEVELS = [("#", "h1"), ("##", "h2"), ("###", "h3")]

# Approximate word limits and token constraints
WORD_CHUNK       = 750      # size of each text chunk (~600 tokens)
WORD_OVERLAP     = 50      # overlapping words between chunks
TOKEN_HARD_LIMIT = 512      # max allowed GPT tokens per chunk
MIN_TOKENS       = 20       # skip chunks smaller than this

PATIENT_RE = re.compile(r"^(.*?)\s*-")
DATE_RE    = re.compile(r'(?:\d{1,2}[-/th|st|nd|rd\s.])?(?:(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|August|Sep|September|Oct|October|Nov|November|Dec|December)[\s,.]*)?(?:(?:\d{1,2})[-/th|st|nd|rd\s,.]*)?(?:\d{2,4})')


# Token encoder for token counting (matches OpenAI GPT models)
enc = tiktoken.get_encoding("cl100k_base")

# ---------------------------- HELPERS -----------------------------------

def num_tokens(text: str) -> int:
    """Returns token count of a string using tiktoken."""
    return len(enc.encode(text))

def is_noise(chunk: str) -> bool:
    """Filters out chunks that are trivial or look like source/captions."""
    if num_tokens(chunk) < MIN_TOKENS:
        return True
    return False

def header_path(md: dict) -> str:
    """Builds a full header path string like 'Section > Subsection > ...'"""
    return " > ".join([md.get("h1", ""), md.get("h2", ""), md.get("h3", "")]).strip(" >")

# ---------------------------- HELPERS -----------------------------------

def header_to_meta(header: str) -> tuple[str|None, str|None]:
    """
    Extract (patient_name, visit_date_iso) from a merged header.

    1) Look for a date first (e.g. '31 March 2009'), parse it to ISO.
    2) Remove that date substring from the header.
    3) Look for a name before the first hyphen.
       Reject anything that contains digits (so dates aren't mistaken).
    """
    # 1) date
    date_match = DATE_RE.search(header)
    visit_date = None
    if date_match:
        try:
            visit_date = dtparse.parse(date_match.group(0)).date().isoformat()
        except Exception:
            visit_date = None

    # 2) strip the date out so it won't confuse the name regex
    hdr_wo_date = DATE_RE.sub("", header)

    # 3) patient name = text before the first hyphen, if it has no digits
    name_match = PATIENT_RE.search(hdr_wo_date)
    patient = None
    if name_match:
        candidate = name_match.group(1).strip()
        if candidate and not any(ch.isdigit() for ch in candidate):
            patient = candidate

    return patient, visit_date


def merge_consecutive_headers(text: str) -> str:
    """
    Scans the document for runs of top-level headers (lines starting with '# '),
    allowing blank lines in between, and collapses each run into one header:

      # A
      # B

      # C

    becomes:

      # A - B - C
    """
    lines = text.splitlines()
    merged = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        # If this line is a top-level header, collect the whole run
        if re.match(r"^#\s+\S+", line):
            headers = []
            header_level = None

            # Gather all headers and skip over blank lines in between
            while i < n and (lines[i].strip() == "" or re.match(r"^#\s+\S+", lines[i])):
                if re.match(r"^#\s+\S+", lines[i]):
                    header_level = "#"  # we only care about one '#' here
                    headers.append(lines[i].lstrip("#").strip())
                i += 1

            # Emit one merged header, then a blank line to separate from body
            merged.append(f"{header_level} {' - '.join(headers)}")
            merged.append("")  # keep one blank line
        else:
            merged.append(line)
            i += 1

    return "\n".join(merged)


# ---------------------------- MAIN PIPELINE -----------------------------

def main(pdf_slug: str):
    DATA_DIR = Path("data")
    MD_PATH  = DATA_DIR / pdf_slug / "organized_cleaned_document.md"
    OUT_PATH = DATA_DIR / pdf_slug / "chunks.json"
    raw = MD_PATH.read_text(encoding="utf-8")
    markdown_text = merge_consecutive_headers(raw)
    # Step 2: Split into sections by headers (h1, h2, h3)
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADER_LEVELS,
        strip_headers=True,
    )
    header_docs = header_splitter.split_text(markdown_text)

    # Step 3: Further split each section into word-based chunks
    word_splitter = RecursiveCharacterTextSplitter(
        chunk_size=WORD_CHUNK,
        chunk_overlap=WORD_OVERLAP,
        length_function=lambda txt: len(txt.split()),  # count by words
    )

    all_chunks = []

    prev_patient: str = "Unknown"
    prev_visit_date: str | None = None

    # Iterate over header sections with progress bar
    for hdoc in tqdm(header_docs, desc="Header blocks"):
        # Create sub-chunks within this header section
        sub_docs = word_splitter.split_documents([hdoc])
        header_txt = header_path(hdoc.metadata)             # ← the merged header
            # parse this header for metadata
        tmp_patient, tmp_date = header_to_meta(header_txt or "")

        # ◆ only update date if we found one
        if tmp_date is not None:
            prev_visit_date = tmp_date

        # ◆ only update patient if we also saw a date in that same header
        #    AND the extracted patient is non-empty
        if tmp_patient and tmp_date is not None:
            prev_patient = tmp_patient

        # carry forward for sub-sections
        patient, visit_date = prev_patient, prev_visit_date

        first_in_section = True   

        for sd in sub_docs:
            text = sd.page_content.strip()
            if is_noise(text):
                continue

            # add header only to the very first chunk of this section
            if first_in_section and header_txt:
                text = f"{header_txt} – {text}"
                first_in_section = False

            # If chunk is too large, split in half until it fits
            while num_tokens(text) > TOKEN_HARD_LIMIT:
                words = text.split()
                midpoint = len(words) // 2

                # NEW  ➜ keep an overlap of WORD_OVERLAP words
                part_words = words[:midpoint]
                text_words = words[midpoint - WORD_OVERLAP:]  # slide back

                part = " ".join(part_words)
                text = " ".join(text_words)

                if not is_noise(part) and num_tokens(part) >= MIN_TOKENS:
                    all_chunks.append(
                        build_chunk(sd.metadata, part, patient, visit_date, pdf_slug)  # ← pass meta
                    )

            # final piece
            all_chunks.append(
                build_chunk(sd.metadata, text, patient, visit_date, pdf_slug)          # ← pass meta
            )


    # Step 4: Save all valid chunks to a .json file
    with OUT_PATH.open("w", encoding="utf-8") as fout:
        json.dump(all_chunks, fout, ensure_ascii=False, indent=2)

    print(f"✅ {len(all_chunks)} chunks written to {OUT_PATH}")

# ---------------------------- CHUNK BUILDER -----------------------------

def build_chunk(meta, text, patient, visit_date, pdf_slug):
    """Builds a single chunk dictionary with metadata and token count."""

    return {
        "id": uuid.uuid4().hex,       # Unique ID for this chunk
        "pdf": pdf_slug,
        "heading": header_path(meta), # Full header path
        "tokens": num_tokens(text),   # Number of GPT tokens
        "text": text,                  # Chunk content
        "patient": patient,          # NEW COLUMN
        "visitdate": visit_date,    # NEW COLUMN (YYYY-MM-DD or None)
    }

# ---------------------------- ENTRY POINT -------------------------------

if __name__ == "__main__":
    main()
