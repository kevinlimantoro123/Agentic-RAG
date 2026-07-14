"""The agent's two tools.

- retrieve_patient_records: stays in IRIS. Thin HTTP client for POST /retrieve,
  which runs RAG2026.BO.RetrieveOperation (HNSW over Embedding.Clinical). No SQL,
  no embedding, no IRIS driver here — IRIS does all of that server-side.
- guideline_search: ported from RAG2026.BO.GuidelineOperation (Tavily, one
  approved domain per source). Pure Python, no IRIS involvement.

Tools are built per request via `make_tools(ctx)` so they can fall back to the
request-level pdf / patient / visit_date filters when the LLM omits them — this
reproduces the arg-merging that RAG2026.BP.AgentProcess.Dispatch did.
"""

import json
import re

import requests
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

from . import config

# Same allow-list as GuidelineOperation.cls (one authoritative domain per source).
GUIDELINE_DOMAINS = {
    "ACE": "ace-hta.gov.sg",
    "NICE": "nice.org.uk",
    "NDF": "ndf.gov.sg",
    "HSA": "hsa.gov.sg",
    "FDA": "fda.gov",
    "NIH": "nih.gov",
    "CDC": "cdc.gov",
}


def make_tools(ctx: dict):
    """Return [retrieve_patient_records, guideline_search] bound to one request's
    context (active pdf + filters)."""

    @tool
    def retrieve_patient_records(
        query: str,
        pdf: str = "",
        patient: str = "",
        visit_date: str = "",
        top_k: int = 0,
    ) -> str:
        """Semantic search over the clinical notes database using HNSW vector
        similarity. Returns matching records with visit date and clinical text.

        Args:
            query: Natural-language search query.
            pdf: Document/PDF slug to search within (defaults to the active document).
            patient: Patient name substring filter (optional).
            visit_date: Date filter: YYYY, YYYY-MM, or YYYY-MM-DD (optional).
            top_k: Maximum records to return (default 5).
        """
        payload = {
            "query": query,
            "pdf": pdf or ctx.get("pdf", ""),
            "patient": patient or ctx.get("patient", ""),
            "visit_date": visit_date or ctx.get("visit_date", ""),
            "top_k": top_k if (top_k and top_k > 0) else ctx.get("top_k", config.DEFAULT_TOP_K),
        }
        try:
            r = requests.post(
                f"{config.IRIS_REST_URL}/retrieve",
                json=payload,
                auth=config.IRIS_AUTH,
                timeout=config.RETRIEVE_TIMEOUT,
            )
            r.raise_for_status()
            return r.text  # JSON array [{label,date,text}], straight from IRIS
        except requests.RequestException as e:
            return json.dumps([{"error": f"retrieve_patient_records failed: {e}"}])

    @tool
    def guideline_search(query: str, resource: str, max_results: int = 3) -> str:
        """Fetch medication guidelines, dosing, or safety information from an
        authoritative clinical resource. Choose the most relevant source.

        Args:
            query: What to look up.
            resource: One of ACE, NICE, NDF, HSA, FDA, NIH, CDC.
            max_results: Maximum snippets to return (default 3).
        """
        res = (resource or "").upper()
        if res not in GUIDELINE_DOMAINS:
            return json.dumps([{"error": f"Unknown resource {resource}"}])

        try:
            maxr = int(max_results)
        except (TypeError, ValueError):
            maxr = 3
        if maxr <= 0:
            maxr = 3

        search = TavilySearch(
            max_results=maxr,
            include_domains=[GUIDELINE_DOMAINS[res]],
            include_raw_content=True,
        )
        resp = search.invoke({"query": query})

        if isinstance(resp, dict) and "results" in resp:
            raw_hits = resp["results"]
        elif isinstance(resp, list):
            raw_hits = resp
        else:
            raw_hits = [resp]

        results, idx = [], 0
        for hit in raw_hits[:maxr]:
            if isinstance(hit, dict):
                content = hit.get("content") or hit.get("raw_content") or ""
                source = hit.get("url", "n/a")
            else:
                content = str(hit)
                source = "n/a"
            text = (content or "").strip()
            if not text:
                continue
            idx += 1
            snippet = re.sub(r"\s+", " ", text)[:500]
            results.append({"label": f"G{idx}", "text": snippet, "source": source})

        return json.dumps(results)

    return [retrieve_patient_records, guideline_search]
