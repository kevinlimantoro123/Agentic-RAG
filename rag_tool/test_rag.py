from __future__ import annotations
"""clinical_rag_demo_no_summ_debug.py

Identical to the previous sample but echoes the context that GPT-4o sees.
"""
"""Web‑search helper plus OpenAI tool spec."""

import re
import argparse, textwrap, os
import openai
from langchain_tavily import TavilySearch      
from sqlalchemy import create_engine, text as sql_text
from dotenv import load_dotenv
import sys
load_dotenv()          # this reads .env in the current working dir

# ---------- IRIS connection details ----------
IRIS_CONN_STR = os.getenv("IRIS_CONN_STR")     # adjust
engine = create_engine(IRIS_CONN_STR)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Please set the OPENAI_API_KEY environment variable")



RESOURCE_DOMAINS = {
    "ACE": "ace-hta.gov.sg",
    "NICE": "nice.org.uk",
    "NDF": "ndf.gov.sg",
    "HSA": "hsa.gov.sg",
    "FDA": "fda.gov",
    "NIH": "nih.gov",
    "CDC": "cdc.gov",
}

def reset() -> None:
    sql = sql_text("CALL Embedding.Reset()")
    with engine.connect() as conn, conn.begin():
        conn.execute(sql)
    

# ---------- Guideline / Web Search ----------
def guideline_search(query: str, resource: str, max_results: int = 3) -> list[dict]:
    resource = resource.upper()
    if resource not in RESOURCE_DOMAINS:
        raise ValueError(f"Unknown resource {resource!r}")
    
    # 2) Invoke Tavily with your new wildcard-style domain
    tool = TavilySearch(
        max_results=max_results,
        include_domains=[RESOURCE_DOMAINS[resource]],
        include_raw_content=True,
    )

    resp = tool.invoke({"query": query})

    # 3) Normalize into a flat list of hits
    if isinstance(resp, dict) and "results" in resp:
        raw_hits = resp["results"]
    elif isinstance(resp, list):
        raw_hits = resp
    else:
        raw_hits = [resp]

    results = []
    for idx, hit in enumerate(raw_hits[:max_results], start=1):
        # 4) try both 'content' and 'raw_content'
        content = ""
        if isinstance(hit, dict):
            content = hit.get("content") or hit.get("raw_content") or ""
            source  = hit.get("url", "n/a")
        else:
            content = str(hit)
            source  = "n/a"
        text = content.strip()
        if not text:
            continue

        # collapse whitespace, truncate
        snippet = re.sub(r"\s+", " ", text)[:500]
        results.append({
            "label":  f"G{idx}",
            "text":   snippet,
            "source": source,
        })

    return results


guideline_search_tool = {
    "type": "function",
    "function": {
        "name": "guideline_search",
        "description": (
            "Look up medication guidelines, dosing or safety information "
            "in authoritative clinical resources."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query":  {"type": "string"},
                "resource": {
                    "type": "string",
                    "enum": list(RESOURCE_DOMAINS.keys()),
                    "description": "Which source to query",
                },
            },
            "required": ["query", "resource"],
        },
    },
}
# ---------- helpers ----------
def retrieve_text_chunks(
    query: str,
    slug: str,
    top_k: int = 5,
    patient: str | None = None,
    visit_date: str | None = None,
) -> list[str]:
    
    filters = ["PDF = :slug"]           # always filter by this PDF
    # Build the WHERE clause dynamically
    params = {"slug": slug, "qtxt": query}

    if patient:
        filters.append("LOWER(Patient) LIKE :pname")
        params["pname"] = f"%{patient.lower()}%"

    if visit_date:
        # allow year- and month-prefix filtering too
        length = len(visit_date)
        if length == 4:  # YYYY
            filters.append("VisitDate LIKE :vdate")
            params["vdate"] = f"{visit_date}-%"
        elif length == 7:  # YYYY-MM
            filters.append("VisitDate LIKE :vdate")
            params["vdate"] = f"{visit_date}%"
        else:  # full YYYY-MM-DD
            filters.append("VisitDate = :vdate")
            params["vdate"] = visit_date

    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

    # No DISTINCT: IRIS's optimizer uses the HNSW index only when the query is
    # a plain TOP-k ORDER BY VECTOR_DOT_PRODUCT pattern. Deduplication is done
    # in Python below.
    sql = sql_text(f"""
        SELECT TOP {top_k} VisitDate, Description
          FROM Embedding.Clinical
         {where_sql}
         ORDER BY VECTOR_DOT_PRODUCT(
                  DescriptionEmbedding,
                  EMBEDDING(:qtxt, 'bge-base-config')
                ) DESC
    """)
    with engine.connect() as conn, conn.begin():
        rows = conn.execute(sql, params).fetchall()

    seen, out = set(), []

    for date_val, raw in rows:
        if not raw:
            continue
        # Clean text
        txt = raw.encode('ascii', 'ignore').decode('ascii')
        norm = re.sub(r"\s+", " ", txt).strip()
        key = (date_val, norm.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "label": f"P{len(out)+1}",
            "date": date_val,
            "text": norm
        })
        if len(out) >= top_k:
            break
    return out


def show_context(chunks: list[str], guides: list[str]) -> None:
    print("\n=== Context Sent to LLM ===\n")
    for i, chunk in enumerate(chunks, 1):
        preview = chunk.replace("\n", " ")[:300]
        more = "…" if len(chunk) > 300 else ""
        print(f"[{i}] {preview}{more}\n")
    if guides:
        print("--- Guideline snippets ---\n")
        for j, g in enumerate(guides, 1):
            preview = g.replace("\n", " ")[:300]
            more = "…" if len(g) > 300 else ""
            print(f"[G{j}] {preview}{more}\n")


# ---------- LLM Call ----------
def answer_question(question: str,
                    chunks:   list[str],
                    guides:   list[str]) -> str:

    pat_ctx = []
    for c in chunks:
        pat_ctx.append(f"[{c['label']}|{c['date']}] {c['text']}")\
    
    gui_ctx = []
    for g in guides:
        gui_ctx.append(f"[{g['label']}|{g['source']}] {g['text']}")
    combined = "\n".join(pat_ctx + gui_ctx)
    
    system_prompt = (
        "You are a careful clinical assistant. Answer the clinician’s question "
        "using BOTH the patient context (marked [P#]) **and** the guideline context "
        "(marked [G#]). If the combined information is still insufficient, reply "
        "'Insufficient data'."
    )
    user_prompt = textwrap.dedent(f"""\
        Patient + Guideline Context:
        {combined}

        ---
        Question: {question}
        Respond clearly and cite any chunk number you referenced like [1], [2]...
    """)
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    chat = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return chat.choices[0].message.content.strip()

# ---------- CLI ----------
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Clinical RAG + Web-Search debug demo"
    )
    p.add_argument("--question", required=True, help="Clinician's question")
    p.add_argument("--top-k",    type=int, default=5, help="# chunks to retrieve")
    p.add_argument(
        "--resource",
        type=str,
        default="NICE",
        help="Which guideline site: " + ",".join(RESOURCE_DOMAINS)
    )

    # NEW optional filters
    p.add_argument("--patient",   help="Patient name (exact or substring)")
    p.add_argument("--date",      help="Visit date (YYYY-MM-DD or YYYY-MM)")

    args = p.parse_args()

    chunks = retrieve_text_chunks(
        args.question,
        top_k=args.top_k,
        patient=args.patient,
        visit_date=args.date,
    )

    if not chunks:
        print("❌ No relevant patient data retrieved.")
        exit(1)

    guides = guideline_search(args.question, args.resource)
    print("=== CONTEXT ===")
    for line in ([f"[{c['label']}|{c['date']}] {c['text']}" for c in chunks] +
                 [f"[{g['label']}|{g['source']}] {g['text']}" for g in guides]):
        print(line)

    show_context(chunks, guides)             # make sure two args are passed
    answer = answer_question(args.question, chunks, guides)
    print("\n=== Assistant Response ===\n")
    print(answer)
    sys.exit(0)