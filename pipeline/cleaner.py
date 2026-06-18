import re
import json
from pathlib import Path
from typing import List, Tuple

def is_boilerplate(heading: str, body: str) -> bool:
    """
    Return True if this (heading, body) pair looks like:
      - A copyright/disclaimer block
      - A list of people/titles with no real “narrative” content
      - Any section you explicitly want to skip
    """

    # A) If heading or body contains common “disclaimer” keywords:
    if re.search(r"\b(©|Copyright|Disclaimer|All rights reserved|Important Notice)\b", heading, re.IGNORECASE):
        return True
    # 2) Source / credits / disclosures
    if re.search(r"(?i)^(Source:|Credits:|Important information|Country/Market Specific Disclosures|Sustainable Investments|Contact Information|disclosure|Explanatory Notes|Subscribe|Disclosures|Important disclosures)", heading, re.IGNORECASE):
        return True
        # F) Jurisdiction-specific disclaimer blocks
    if re.search(
        r"(?i)(note to recipients and investors in|"
        r"prohibition of sales to|"
        r"for collective investment schemes|"
        r"regulated (only )?by the|"
        r"licensed and (supervised|regulated) by|"
        r"monetary authority of|"
        r"securities and futures commission|"
        r"financial services authority|"
        r"priips|"
        r"personal data protection act|"
        r"banking ordinance)",
        heading + " " + body,
    ):
        return True

    # C) If the heading itself is “Source:” or “Credits” or “Editorial Team”:
    if re.fullmatch(r"(Source|Credits|Editorial Team)", heading, re.IGNORECASE):
        return True

    # D) If body contains repetitive chart‐axis text (very short lines of digits or “Figure X: …”)
    if re.match(r"(?i)^figure\s+\d+[:\s]", body.strip()) and len(body.split()) < 12:
        return True
    # Otherwise, keep it
    return False



def clean_text_block(text: str, min_line_length: int = 5) -> str:
    """
    Cleans a single text block by:
      - Dropping purely numeric/percent/chart lines
      - Removing URLs
      - Converting Markdown links [text](url) → text
      - Dropping lines shorter than min_line_length
      - Collapsing multiple spaces
    """
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # 1) Drop purely numeric/percent lines (e.g., "4.40% 4.41% 3.85%")
        if re.fullmatch(r"[\d\.\-%\s]+", line):
            continue

        # 2) Remove URLs (http://, https://, www.)
        line = re.sub(r"https?://\S+|www\.\S+", "", line)

        # 3) Convert Markdown links [text](url) → text
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)

        # 4) Collapse multiple spaces to one
        line = re.sub(r"\s{2,}", " ", line)

        # 5) Drop very short lines
        if len(line) < min_line_length:
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def load_and_group_elements(
    extracted_base_dir: str,
    pdf_name: str,
) -> List[Tuple[str, str, str]]:
    """
    1) Read document_metadata.json under extracted_base_dir/pdf_name/
    2) For each element of type Title, Text, NarrativeText, or ListItem,
       read its mini .txt file, clean it, and group by section_key.
    3) Return a list of (section_key, elem_type, cleaned_text) tuples,
       sorted by (section_key, page_number, element_index).
    """
    base_dir = Path(extracted_base_dir) / pdf_name
    metadata_path = base_dir / "document_metadata.json"

    if not metadata_path.exists():
        raise FileNotFoundError(f"Cannot find metadata at {metadata_path}")

    doc_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    elements = doc_meta.get("elements_metadata", [])
    if not elements:
        raise ValueError("No elements found in metadata.")

    grouped: List[Tuple[str, str, str, int, int]] = []
    # Each tuple: (section_key, elem_type, cleaned_text, page_num, elem_index)

    for elem in elements:
        elem_type = elem.get("element_type")
        page_num = elem.get("page_number", -1)
        elem_index = elem.get("element_index", -1)
        # if elem_type == "Image" or elem_type == "Table":
            # content_path = elem.get("image_path")
        
        content_path = elem.get("content_path")
        if not content_path:
            continue

        # Determine section_key
        if page_num >= 0:
            section_key = f"Page_{page_num}"
        else:
            section_key = "Unspecified"

        # Only include Title, Text, NarrativeText, or ListItem
        if elem_type not in ("Title", "NarrativeText", "ListItem"):
            continue
        if elem_type == "Image" or elem_type == "Table":
            # the extractor usually leaves content_path pointing to the image file
            # create a Markdown image tag; use file-name as alt-text
            img_path = Path(content_path)              # e.g. .../page_3_img_12.png
            img_path = img_path.relative_to(base_dir)
            md_image = f"![{img_path.stem}]({img_path.as_posix()})"
            cleaned_text = md_image
        else:
            text_file_path = Path(content_path)
            if not text_file_path.exists():
                continue
            raw_text     = text_file_path.read_text(encoding="utf-8")
            cleaned_text = clean_text_block(raw_text)
            if not cleaned_text.strip():
                continue

        grouped.append((section_key, elem_type, cleaned_text, page_num, elem_index))

    # Sort by (section_key, page_num, elem_index)
    grouped.sort(key=lambda x: (x[3], x[4]))

    # Discard page_num, elem_index in final output
    return [(sec, etype, txt) for sec, etype, txt, _, _ in grouped]


def merge_repeated_titles(
    grouped: List[Tuple[str, str, str]]
) -> List[Tuple[str, str]]:
    """
    From a list of (section_key, elem_type, cleaned_text),
    produce a list of (heading, paragraph) tuples. Consecutive identical
    titles are merged by concatenating their paragraphs.
    """
    final_segments: List[Tuple[str, str]] = []
    current_heading = None
    current_body_parts: List[str] = []

    for section_key, elem_type, text in grouped:
        if elem_type == "Title":
            # Flush previous segment if any
            if current_heading is not None:
                body = "\n\n".join(current_body_parts).strip()
                final_segments.append((current_heading, body))
                current_body_parts = []

            heading = text.strip()
            # If the last appended heading is identical, keep using it
            if final_segments and final_segments[-1][0] == heading:
                current_heading = heading
            else:
                current_heading = heading

        else:  # elem_type in ("Text", "NarrativeText", "ListItem")
            if current_heading is None:
                current_heading = "Unspecified"
            current_body_parts.append(text.strip())

    # Flush the very last segment
    if current_heading is not None:
        body = "\n\n".join(current_body_parts).strip()
        final_segments.append((current_heading, body))

    return final_segments


def write_final_markdown(
    segments: List[Tuple[str, str]],
    output_path: Path
):
    """
    Given a list of (heading, paragraph) tuples, write them to output_path as Markdown.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for heading, body in segments:
            f.write(f"# {heading}\n\n")
            if body:
                f.write(body.strip() + "\n\n")


def organize_and_clean_by_section(
    extracted_base_dir: str,
    pdf_name: str,
    output_filename: str = "organized_cleaned_document.md",
    debug: bool = False
):
    base_dir = Path(extracted_base_dir) / pdf_name
    output_path = base_dir / output_filename

    # 1) Load and group elements (Title/Text/NarrativeText/ListItem)
    grouped = load_and_group_elements(extracted_base_dir, pdf_name)

    # 2) Merge repeated titles
    raw_segments = merge_repeated_titles(grouped)
    # raw_segments is now List[ (heading, body) ]

    # 3) Filter out boilerplate
    filtered_segments = []
    for heading, body in raw_segments:
        if debug:
            print(f"🧪 Checking section: {heading[:50]}...")
        if is_boilerplate(heading, body):
            print(f"🚫 Skipping section: {heading[:40]}' (len={len(body)}): {body[:60]!r}")
            continue
        filtered_segments.append((heading, body))

    # 4) Write only the filtered segments
    write_final_markdown(filtered_segments, output_path)

    print(f"✅ Organized & cleaned Markdown saved at:\n  {output_path.resolve()}")



if __name__ == "__main__":
    extracted_base_dir = "data"
    pdf_name = "Sample_Notes"

    organize_and_clean_by_section(extracted_base_dir, pdf_name, debug=True)
