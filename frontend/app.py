"""
Thin Streamlit client for the RAG2026 IRIS production.

This UI does NO processing itself — it just calls the IRIS REST endpoints:
  POST /ingest  {slug, pdf_base64}            -> Ingest Service -> Ingest Process
  POST /query   {question, pdf, patient, ...} -> Query Service  -> Agent Process
  GET  /health

Config via env (or .env):
  IRIS_REST_URL   default http://localhost:52773/csp/rag2026
  IRIS_USER       default SuperUser
  IRIS_PASSWORD   default SYS
"""

import base64
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

IRIS_REST_URL = os.getenv("IRIS_REST_URL", "http://localhost:52773/csp/rag2026").rstrip("/")
IRIS_USER = os.getenv("IRIS_USER", "SuperUser")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "SYS")
AUTH = (IRIS_USER, IRIS_PASSWORD)


def iris_get(path: str, timeout: int = 30):
    return requests.get(f"{IRIS_REST_URL}{path}", auth=AUTH, timeout=timeout)


def iris_post(path: str, payload: dict, timeout: int):
    return requests.post(f"{IRIS_REST_URL}{path}", json=payload, auth=AUTH, timeout=timeout)


st.set_page_config(page_title="Agentic Clinical RAG (IRIS)", layout="wide")
st.title("📄→🧠 Agentic Clinical RAG — IRIS Interoperability")
st.caption(f"Thin client → {IRIS_REST_URL}")

if "slug" not in st.session_state:
    st.session_state["slug"] = ""

# ── STEP 1: upload + ingest (via IRIS) ───────────────────────────────────────
uploaded = st.file_uploader("Upload clinical PDF", type="pdf")
if uploaded is not None:
    slug = Path(uploaded.name).stem
    st.write(f"Slug: `{slug}`")
    if st.button("⬆️ Ingest into IRIS"):
        pdf_b64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
        with st.spinner("Ingesting via IRIS (extract → clean → chunk → load)…"):
            try:
                resp = iris_post("/ingest", {"slug": slug, "pdf_base64": pdf_b64}, timeout=900)
            except requests.RequestException as e:
                st.error(f"Request to IRIS failed: {e}")
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["slug"] = data.get("slug", slug)
                    st.success(f"✅ Loaded {data.get('rows_inserted', '?')} chunks for '{st.session_state['slug']}'.")
                else:
                    st.error(f"Ingest failed ({resp.status_code}): {resp.text}")

# ── Sidebar: query filters ───────────────────────────────────────────────────
with st.sidebar:
    st.header("🩺 Query Filters")
    pdf = st.text_input("PDF slug to query", value=st.session_state.get("slug", ""))
    patient = st.text_input("Patient name (optional)")
    visit_date = st.text_input("Visit date — YYYY / YYYY-MM / YYYY-MM-DD (optional)")
    resource = st.selectbox(
        "Preferred guideline source",
        ["ACE", "NICE", "NDF", "HSA", "FDA", "NIH", "CDC"],
        index=1,
        help="The agent may choose a different source if more appropriate.",
    )
    top_k = st.selectbox("Top k results", list(range(1, 11)), index=4)

    st.divider()
    if st.button("Check IRIS health"):
        try:
            r = iris_get("/health")
            (st.success if r.status_code == 200 else st.error)(f"{r.status_code}: {r.text}")
        except requests.RequestException as e:
            st.error(str(e))

# ── Main: ask the agent (via IRIS) ───────────────────────────────────────────
st.title("🤖 Ask the agent")
st.caption("GPT-4o runs the tool loop inside IRIS — patient records (HNSW) + guidelines.")

question = st.text_input("Enter your clinical question:")

if st.button("Run Agent"):
    if not question.strip():
        st.warning("Please enter a question.")
    elif not pdf.strip():
        st.warning("Enter a PDF slug in the sidebar (ingest a PDF first).")
    else:
        payload = {
            "question": question,
            "pdf": pdf,
            "patient": patient or "",
            "visit_date": visit_date or "",
            "resource": resource or "",
            "top_k": top_k,
        }
        with st.spinner("🤖 Agent reasoning in IRIS…"):
            try:
                resp = iris_post("/query", payload, timeout=180)
            except requests.RequestException as e:
                st.error(f"Request to IRIS failed: {e}")
                resp = None

        if resp is not None:
            if resp.status_code != 200:
                st.error(f"Query failed ({resp.status_code}): {resp.text}")
            else:
                data = resp.json()
                tool_log = data.get("tool_log", [])

                with st.expander("🔧 Agent tool calls", expanded=False):
                    if not tool_log:
                        st.write("_Agent answered without calling any tools._")
                    for i, ev in enumerate(tool_log, 1):
                        tool = ev.get("tool", "?")
                        st.markdown(f"**Step {i} — `{tool}`**")
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("**Arguments**")
                            st.json(ev.get("args", {}))
                        with c2:
                            st.markdown("**Result**")
                            result = ev.get("result", [])
                            if tool == "retrieve_patient_records" and isinstance(result, list):
                                for rec in result:
                                    st.markdown(
                                        f"**[{rec.get('label', '?')}|{rec.get('date', '?')}]** "
                                        f"{str(rec.get('text', ''))[:300]}…"
                                    )
                            elif tool == "guideline_search" and isinstance(result, list):
                                for rec in result:
                                    st.markdown(
                                        f"**[{rec.get('label', '?')}|{rec.get('source', 'n/a')}]** "
                                        f"{str(rec.get('text', ''))[:300]}…"
                                    )
                            else:
                                st.json(result)

                st.markdown("### 💬 Answer")
                st.markdown(data.get("answer", ""))
