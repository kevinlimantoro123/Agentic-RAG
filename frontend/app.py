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
import threading
import time
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

IRIS_REST_URL = os.getenv("IRIS_REST_URL", "http://localhost:52773/csp/rag2026").rstrip("/")
IRIS_USER = os.getenv("IRIS_USER", "SuperUser")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "SYS")
AUTH = (IRIS_USER, IRIS_PASSWORD)

# ── Extractor sidecar (must be started separately — NOT auto-started) ─────────
# Run it yourself before ingesting, e.g.:
#   python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800
SIDECAR_HOST = os.getenv("SIDECAR_HOST", "127.0.0.1")
SIDECAR_PORT = int(os.getenv("SIDECAR_PORT", "8800"))
SIDECAR_HEALTH = f"http://{SIDECAR_HOST}:{SIDECAR_PORT}/health"


def iris_get(path: str, params: dict | None = None, timeout: int = 30):
    return requests.get(f"{IRIS_REST_URL}{path}", auth=AUTH, params=params, timeout=timeout)


def iris_post(path: str, payload: dict, timeout: int):
    return requests.post(f"{IRIS_REST_URL}{path}", json=payload, auth=AUTH, timeout=timeout)


def fetch_list(path: str, key: str, params: dict | None = None) -> list:
    """GET a {key: [...]} list endpoint; return [] on any failure."""
    try:
        r = iris_get(path, params=params)
        if r.status_code == 200:
            return r.json().get(key, [])
    except requests.RequestException:
        pass
    return []


def call_with_timer(label: str, fn):
    """Run a blocking call on a worker thread while ticking a live elapsed timer
    on the main thread.

    A bare st.spinner only animates while Streamlit is streaming updates, so a
    single long request (ingest queue, agent query) leaves it frozen for the
    whole wait. Driving an st.empty() counter from the main thread guarantees
    the UI keeps visibly moving. Returns fn()'s result; re-raises its exception.
    """
    box: dict = {}

    def worker():
        try:
            box["result"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    ph = st.empty()
    start = time.time()
    while t.is_alive():
        ph.info(f"⏳ {label}… {int(time.time() - start)}s")
        time.sleep(0.5)
    t.join()
    ph.empty()

    if "error" in box:
        raise box["error"]
    return box.get("result")


def sidecar_reachable() -> bool:
    """Passive check — the sidecar must be started separately (no auto-start)."""
    try:
        return requests.get(SIDECAR_HEALTH, timeout=2).status_code == 200
    except requests.RequestException:
        return False


st.set_page_config(page_title="Agentic Clinical RAG (IRIS)", layout="wide")
st.title("Agentic Clinical RAG with IRIS")

if sidecar_reachable():
    st.caption(f"✅ Extractor sidecar reachable @ {SIDECAR_HOST}:{SIDECAR_PORT}")
else:
    st.warning(
        f"⚠️ Extractor sidecar not reachable @ {SIDECAR_HOST}:{SIDECAR_PORT} — "
        "start it before ingesting:  "
        "`python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800`"
    )

if "slug" not in st.session_state:
    st.session_state["slug"] = ""

# ── STEP 1: upload + ingest (via IRIS) ───────────────────────────────────────
uploaded = st.file_uploader("Upload clinical PDF", type="pdf")
if uploaded is not None:
    slug = Path(uploaded.name).stem
    st.write(f"Slug: `{slug}`")
    if st.button("Ingest into IRIS"):
        pdf_b64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
        # 1) Queue the job (returns immediately with a job id).
        try:
            resp = call_with_timer(
                "Queueing ingest in IRIS",
                lambda: iris_post("/ingest", {"slug": slug, "pdf_base64": pdf_b64}, timeout=60),
            )
        except requests.RequestException as e:
            st.error(f"Request to IRIS failed: {e}")
            resp = None

        if resp is not None and resp.status_code != 200:
            st.error(f"Ingest failed to start ({resp.status_code}): {resp.text}")
        elif resp is not None:
            job_id = resp.json().get("job_id")
            # 2) Poll for completion (no long HTTP request to time out).
            status_box = st.empty()
            done = False
            poll_start = time.time()
            for _ in range(0):  # up to ~20 min at 2s intervals
                time.sleep(2)
                try:
                    s = iris_get("/ingest/status", params={"id": job_id})
                except requests.RequestException as e:
                    status_box.warning(f"status check failed: {e}")
                    continue
                if s.status_code != 200:
                    status_box.warning(f"status check returned {s.status_code}")
                    continue
                d = s.json()
                state = d.get("status")
                status_box.info(f"⏳ Ingesting via IRIS — status: {state} ({int(time.time() - poll_start)}s)")
                if state == "Done":
                    st.session_state["slug"] = d.get("slug", slug)
                    st.success(f"✅ Loaded {d.get('rows_inserted', '?')} chunks for '{st.session_state['slug']}'.")
                    done = True
                    break
                if state == "Error":
                    st.error(f"Ingest error: {d.get('error', '(no detail)')}")
                    done = True
                    break
                if state == "NotFound":
                    st.error("Ingest job not found.")
                    done = True
                    break
            if not done:
                st.warning("Still running after the wait window — check the production Visual Trace / sidecar.log.")

# ── Sidebar: query filters ───────────────────────────────────────────────────
with st.sidebar:
    st.header("🩺 Query Filters")

    # PDF dropdown populated from IRIS.
    pdf_options = fetch_list("/pdfs", "pdfs")
    choices = [""] + pdf_options
    default_slug = st.session_state.get("slug", "")
    idx = choices.index(default_slug) if default_slug in choices else 0
    pdf = st.selectbox("PDF to query", choices, index=idx)
    if not pdf_options:
        st.caption("No documents loaded yet — ingest a PDF to populate this list.")

    # Patient dropdown for the chosen PDF.
    patient_options = fetch_list("/patients", "patients", params={"pdf": pdf}) if pdf else []
    patient = st.selectbox("Patient (optional)", [""] + patient_options, index=0)

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
        st.warning("Select a PDF from the sidebar.")
    else:
        payload = {
            "question": question,
            "pdf": pdf,
            "patient": patient or "",
            "visit_date": visit_date or "",
            "resource": resource or "",
            "top_k": top_k,
        }
        try:
            resp = call_with_timer(
                "Agent reasoning in IRIS",
                lambda: iris_post("/query", payload, timeout=180),
            )
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
