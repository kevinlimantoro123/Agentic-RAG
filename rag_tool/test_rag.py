"""Web-search and IRIS vector-retrieval helpers used by the agentic RAG loop.

Exposes:
  - retrieve_text_chunks: HNSW vector search over Embedding.Clinical
  - guideline_search:      authoritative web sources via Tavily
  - RESOURCE_DOMAINS:      allowed guideline domains
  - reset:                 clear the Embedding tables

The agent's behaviour is driven by the single SYSTEM_PROMPT in agent.py;
this module only provides the tools the agent calls.
"""
from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()  # reads .env in the current working dir

# ---------- IRIS connection ----------
IRIS_CONN_STR = os.getenv("IRIS_CONN_STR")
engine = create_engine(IRIS_CONN_STR)


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
    """Clear all loaded data.

    Runs the DELETEs directly rather than via a stored procedure — the
    Embedding.Reset() proc crashed the SQL connection, while plain DELETEs are
    instant and reliable. Each table is cleared independently so a fresh DB
    (where a table may not exist yet) doesn't error.
    """
    for tbl in ("Embedding.Clinical", "Embedding.DocumentMeta"):
        try:
            with engine.connect() as conn, conn.begin():
                conn.execute(sql_text(f"DELETE FROM {tbl}"))
        except SQLAlchemyError:
            # Table doesn't exist yet (nothing loaded) — nothing to clear.
            pass


# ---------- Guideline / Web Search ----------
def guideline_search(query: str, resource: str, max_results: int = 3) -> list[dict]:
    resource = resource.upper()
    if resource not in RESOURCE_DOMAINS:
        raise ValueError(f"Unknown resource {resource!r}")

    tool = TavilySearch(
        max_results=max_results,
        include_domains=[RESOURCE_DOMAINS[resource]],
        include_raw_content=True,
    )

    resp = tool.invoke({"query": query})

    # Normalize into a flat list of hits
    if isinstance(resp, dict) and "results" in resp:
        raw_hits = resp["results"]
    elif isinstance(resp, list):
        raw_hits = resp
    else:
        raw_hits = [resp]

    results = []
    for idx, hit in enumerate(raw_hits[:max_results], start=1):
        # try both 'content' and 'raw_content'
        content = ""
        if isinstance(hit, dict):
            content = hit.get("content") or hit.get("raw_content") or ""
            source = hit.get("url", "n/a")
        else:
            content = str(hit)
            source = "n/a"
        text = content.strip()
        if not text:
            continue

        # collapse whitespace, truncate
        snippet = re.sub(r"\s+", " ", text)[:500]
        results.append({
            "label": f"G{idx}",
            "text": snippet,
            "source": source,
        })

    return results


# ---------- Patient record retrieval (HNSW vector search) ----------
def retrieve_text_chunks(
    query: str,
    slug: str,
    top_k: int = 5,
    patient: str | None = None,
    visit_date: str | None = None,
) -> list[dict]:

    query = (query or "").strip()
    filters = ["PDF = :slug"]           # always filter by this PDF
    params = {"slug": slug}

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

    if query:
        # Semantic ranking via vector search. No DISTINCT: IRIS's optimizer uses
        # the HNSW index only for a plain TOP-k ORDER BY VECTOR_DOT_PRODUCT
        # pattern. Deduplication is done in Python below.
        params["qtxt"] = query
        order_sql = """ORDER BY VECTOR_DOT_PRODUCT(
                  DescriptionEmbedding,
                  EMBEDDING(:qtxt, 'bge-base-config')
                ) DESC"""
    else:
        # No search text (e.g. "list this patient's records") — passing '' to
        # EMBEDDING is a fatal error in IRIS, so fall back to recency ordering.
        order_sql = "ORDER BY VisitDate DESC"

    sql = sql_text(f"""
        SELECT TOP {top_k} VisitDate, Description
          FROM Embedding.Clinical
         {where_sql}
         {order_sql}
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
            "text": norm,
        })
        if len(out) >= top_k:
            break
    return out
