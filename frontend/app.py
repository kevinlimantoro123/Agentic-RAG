"""
Streamlit client for the RAG2026 IRIS production.

This UI does NO processing itself — it just calls the IRIS REST endpoints and the
out-of-IRIS LangGraph agent service:
  POST /ingest  {slug, pdf_base64}            -> Ingest Service -> Ingest Process   (IRIS)
  POST /query   {question, thread_id, pdf, …} -> LangGraph agent                     (agent)
  GET  /health

Config via env (or .env):
  IRIS_REST_URL   default http://localhost:52773/csp/rag2026
  IRIS_USER       default SuperUser
  IRIS_PASSWORD   default SYS
  AGENT_URL       default http://localhost:8001
"""

import base64
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

IRIS_REST_URL = os.getenv("IRIS_REST_URL", "http://localhost:52773/csp/rag2026").rstrip("/")
IRIS_USER = os.getenv("IRIS_USER", "SuperUser")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "SYS")
# The agentic query loop runs out-of-IRIS in the LangGraph agent service
# (agent/server.py). Ingest, pdfs, patients, health and dedup still hit IRIS;
# only /query is served by the agent. Retrieval itself remains in IRIS — the
# agent calls IRIS's /retrieve internally.
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001").rstrip("/")
# Only send HTTP Basic auth when a user is configured. When the IRIS web
# application is set to Unauthenticated (e.g. behind IIS, which rejects the
# Authorization header), an empty IRIS_USER disables the header entirely.
AUTH = (IRIS_USER, IRIS_PASSWORD) if IRIS_USER else None

# ── Extractor sidecar (auto-started below) ───────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SIDECAR_HOST = os.getenv("SIDECAR_HOST", "127.0.0.1")
SIDECAR_PORT = int(os.getenv("SIDECAR_PORT", "8800"))
SIDECAR_STRATEGY = os.getenv("SIDECAR_STRATEGY", "fast")
SIDECAR_HEALTH = f"http://{SIDECAR_HOST}:{SIDECAR_PORT}/health"
AUTOSTART_SIDECAR = os.getenv("AUTOSTART_SIDECAR", "1") == "1"

USER_AVATAR = "🧑‍⚕️"
ASSISTANT_AVATAR = "🩺"

_TOOL_LABELS = {
    "retrieve_patient_records": "Patient records",
    "guideline_search": "Clinical guidelines",
}


# ── Backend helpers (unchanged contract) ─────────────────────────────────────
def iris_get(path: str, params: dict | None = None, timeout: int = 30):
    return requests.get(f"{IRIS_REST_URL}{path}", auth=AUTH, params=params, timeout=timeout)


def iris_post(path: str, payload: dict, timeout: int):
    return requests.post(f"{IRIS_REST_URL}{path}", json=payload, auth=AUTH, timeout=timeout)


def agent_post(path: str, payload: dict, timeout: int):
    """POST to the out-of-IRIS LangGraph agent service (no IRIS auth)."""
    return requests.post(f"{AGENT_URL}{path}", json=payload, timeout=timeout)


def fetch_list(path: str, key: str, params: dict | None = None) -> list:
    """GET a {key: [...]} list endpoint; return [] on any failure."""
    try:
        r = iris_get(path, params=params)
        if r.status_code == 200:
            return r.json().get(key, [])
    except requests.RequestException:
        pass
    return []


def fetch_value(path: str, key: str, default=None, params: dict | None = None):
    """GET a {key: value} endpoint; return `default` on any failure."""
    try:
        r = iris_get(path, params=params)
        if r.status_code == 200:
            return r.json().get(key, default)
    except requests.RequestException:
        pass
    return default


@st.cache_resource(show_spinner=False)
def ensure_sidecar() -> str:
    """Start the extractor sidecar once per Streamlit server process (idempotent).

    Runs only when it isn't already reachable, so manually-started sidecars and
    Streamlit reruns never spawn duplicates. Logs go to <repo>/sidecar.log.
    """
    try:
        if requests.get(SIDECAR_HEALTH, timeout=2).status_code == 200:
            return "already running"
    except requests.RequestException:
        pass

    env = os.environ.copy()
    env["SIDECAR_STRATEGY"] = SIDECAR_STRATEGY
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)

    try:
        logfile = open(REPO_ROOT / "sidecar.log", "a", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "sidecar.extract_service:app",
             "--host", SIDECAR_HOST, "--port", str(SIDECAR_PORT)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=logfile,
            stderr=logfile,
            creationflags=creationflags,
        )
    except Exception as e:  # noqa: BLE001
        return f"failed to launch: {e}"

    # First launch imports unstructured/torch — that's slow, so poll briefly.
    for _ in range(24):
        time.sleep(0.5)
        try:
            if requests.get(SIDECAR_HEALTH, timeout=2).status_code == 200:
                return "started"
        except requests.RequestException:
            continue
    return "starting (first launch is slow — see sidecar.log)"


def _run_ingest(slug: str, pdf_b64: str):
    """Queue the ingest job and poll until done. Renders status inline."""
    try:
        resp = iris_post("/ingest", {"slug": slug, "pdf_base64": pdf_b64}, timeout=60)
    except requests.RequestException as e:
        st.error(f"Request to IRIS failed: {e}")
        return

    if resp.status_code != 200:
        st.error(f"Ingest failed to start ({resp.status_code}): {resp.text}")
        return

    _d = resp.json()
    if _d.get("status") == "Duplicate":
        st.session_state["slug"] = _d.get("slug", slug)
        _mode = _d.get("mode", "Slug")
        _existing = _d.get("slug", slug)
        _chunks = _d.get("rows_inserted", "?")
        if _mode == "Content":
            st.warning(
                f"This file's contents are already loaded as '{_existing}' "
                f"({_chunks} chunks) — skipped duplicate ingest (Content mode)."
            )
        else:
            st.warning(
                f"'{_existing}' is already loaded in IRIS "
                f"({_chunks} chunks) — skipped duplicate ingest (Slug mode)."
            )
        return

    job_id = _d.get("job_id")
    status_box = st.empty()
    done = False
    with st.spinner("Ingesting via IRIS (extract → clean → chunk → load)…"):
        for _ in range(600):  # up to ~20 min at 2s intervals
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
            status_box.info(f"Status: {state}")
            if state == "Done":
                st.session_state["slug"] = d.get("slug", slug)
                status_box.success(
                    f"Loaded {d.get('rows_inserted', '?')} chunks for '{st.session_state['slug']}'."
                )
                done = True
                break
            if state == "Error":
                status_box.error(f"Ingest error: {d.get('error', '(no detail)')}")
                done = True
                break
            if state == "NotFound":
                status_box.error("Ingest job not found.")
                done = True
                break
    if not done:
        st.warning("Still running after the wait window — check the Visual Trace / sidecar.log.")


# ── Page setup + theme ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Clinical Evidence Assistant",
    page_icon="✚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root {
        --ce-bg: #eef1f6;
        --ce-surface: #ffffff;
        --ce-border: #e2e6ee;
        --ce-ink: #1b2431;
        --ce-ink-soft: #5c6673;
        --ce-accent: #0f7a6c;
        --ce-accent-soft: #e6f3f0;
      }

      /* Base type + canvas */
      html, body, [data-testid="stAppViewContainer"], [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                     Helvetica, Arial, sans-serif;
      }
      [data-testid="stAppViewContainer"] { background: var(--ce-bg); }
      [data-testid="stHeader"] { background: transparent; }
      .block-container {
        max-width: 880px;
        padding-top: 1.4rem;
        padding-bottom: 7rem;
      }
      #MainMenu, footer { visibility: hidden; }

      /* Sidebar */
      [data-testid="stSidebar"] {
        background: var(--ce-surface);
        border-right: 1px solid var(--ce-border);
      }
      [data-testid="stSidebar"] .block-container { padding-top: 1.1rem; }

      .side-brand {
        display: flex; align-items: center; gap: .6rem;
        padding: .2rem 0 1rem;
        border-bottom: 1px solid var(--ce-border);
        margin-bottom: .4rem;
      }
      .side-brand-mark {
        width: 34px; height: 34px; border-radius: 9px;
        background: var(--ce-accent); color: #fff;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.25rem; font-weight: 700;
      }
      .side-brand-title { font-size: .98rem; font-weight: 700; color: var(--ce-ink); line-height: 1.1; }
      .side-brand-sub { font-size: .74rem; color: var(--ce-ink-soft); }

      .side-section {
        font-size: .70rem; font-weight: 700; letter-spacing: .09em;
        text-transform: uppercase; color: #93a0b0;
        margin: 1.25rem 0 .35rem;
      }

      /* App header */
      .app-header { padding: .1rem 0 .2rem; }
      .app-header-title {
        font-size: 1.5rem; font-weight: 700; color: var(--ce-ink);
        letter-spacing: -.01em;
      }
      .app-header-sub { font-size: .92rem; color: var(--ce-ink-soft); margin-top: .1rem; }
      .conv-meta {
        font-size: .78rem; color: var(--ce-ink-soft);
        display: flex; align-items: center; height: 100%;
      }
      .conv-dot {
        display: inline-block; width: 7px; height: 7px; border-radius: 50%;
        background: var(--ce-accent); margin-right: .45rem;
      }

      hr { border-color: var(--ce-border); }

      /* Chat messages as clean cards */
      [data-testid="stChatMessage"] {
        background: var(--ce-surface);
        border: 1px solid var(--ce-border);
        border-radius: 14px;
        padding: .85rem 1.05rem;
        margin-bottom: .7rem;
        box-shadow: 0 1px 2px rgba(16,24,40,.04);
      }
      [data-testid="stChatMessage"] p { color: var(--ce-ink); }

      /* Empty state */
      .ce-empty {
        border: 1px dashed var(--ce-border);
        border-radius: 16px;
        background: var(--ce-surface);
        padding: 1.6rem 1.5rem;
        color: var(--ce-ink-soft);
      }
      .ce-empty h4 { color: var(--ce-ink); margin: 0 0 .4rem; font-size: 1.02rem; }
      .ce-chip {
        display: inline-block; margin: .25rem .35rem 0 0;
        padding: .3rem .7rem; border-radius: 999px;
        background: var(--ce-accent-soft); color: var(--ce-accent);
        font-size: .82rem; font-weight: 500;
      }

      /* Buttons */
      .stButton > button {
        border-radius: 9px;
        border: 1px solid var(--ce-border);
        background: var(--ce-surface);
        color: var(--ce-ink);
        font-weight: 500;
        transition: border-color .15s ease, color .15s ease;
      }
      .stButton > button:hover {
        border-color: var(--ce-accent);
        color: var(--ce-accent);
      }
      .stButton > button[kind="primary"] {
        background: var(--ce-accent);
        border-color: var(--ce-accent);
        color: #fff;
      }
      .stButton > button[kind="primary"]:hover {
        background: #0c6558; border-color: #0c6558; color: #fff;
      }

      /* Chat input */
      [data-testid="stBottom"] > div { background: transparent; }
      [data-testid="stChatInput"] {
        border: 1px solid var(--ce-border);
        border-radius: 12px;
        background: var(--ce-surface);
        box-shadow: 0 2px 10px rgba(16,24,40,.06);
      }
      [data-testid="stChatInput"] textarea { font-size: .96rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ────────────────────────────────────────────────────────────
if "slug" not in st.session_state:
    st.session_state["slug"] = ""
if "replace_pending" not in st.session_state:
    st.session_state["replace_pending"] = False
if "replace_payload" not in st.session_state:
    st.session_state["replace_payload"] = None
# Conversation key for the agent's multi-turn memory. Stable for the session so
# follow-up questions share history; "New conversation" rotates it for a fresh start.
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = str(uuid4())
# Local display history for the current conversation. The agent keeps its own
# authoritative memory keyed by thread_id; this list is purely what we render.
if "messages" not in st.session_state:
    st.session_state["messages"] = []


def _render_tool_log(tool_log: list):
    """Collapsible panel of the retrieval steps behind an answer."""
    label = "Retrieval & sources" if tool_log else "No tools used for this answer"
    with st.expander(label, expanded=False):
        if not tool_log:
            st.caption("Answered from conversation context alone.")
            return
        for i, ev in enumerate(tool_log, 1):
            tool = ev.get("tool", "?")
            st.markdown(f"**{i}. {_TOOL_LABELS.get(tool, tool)}**")
            c1, c2 = st.columns(2)
            with c1:
                st.caption("Query")
                st.json(ev.get("args", {}))
            with c2:
                st.caption("Results")
                result = ev.get("result", [])
                if tool == "retrieve_patient_records" and isinstance(result, list):
                    for rec in result:
                        st.markdown(
                            f"**[{rec.get('label', '?')} · {rec.get('date', '?')}]** "
                            f"{str(rec.get('text', ''))[:300]}…"
                        )
                elif tool == "guideline_search" and isinstance(result, list):
                    for rec in result:
                        st.markdown(
                            f"**[{rec.get('label', '?')} · {rec.get('source', 'n/a')}]** "
                            f"{str(rec.get('text', ''))[:300]}…"
                        )
                else:
                    st.json(result)


def _render_message(msg: dict):
    avatar = USER_AVATAR if msg["role"] == "user" else ASSISTANT_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("tool_log") is not None:
            _render_tool_log(msg["tool_log"])


# ── Sidebar: documents, query context, settings ──────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="side-brand">
          <div class="side-brand-mark">✚</div>
          <div>
            <div class="side-brand-title">Clinical Evidence</div>
            <div class="side-brand-sub">Assistant</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Documents ────────────────────────────────────────────────────────────
    st.markdown("<div class='side-section'>Documents</div>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload clinical PDF", type="pdf", label_visibility="collapsed")

    # Reset the pending-replace state when a different file is uploaded.
    if uploaded is not None:
        _uploaded_slug = Path(uploaded.name).stem
        if st.session_state["replace_payload"] is not None:
            if st.session_state["replace_payload"].get("slug") != _uploaded_slug:
                st.session_state["replace_pending"] = False
                st.session_state["replace_payload"] = None

    if uploaded is not None:
        slug = Path(uploaded.name).stem
        st.caption(f"Slug: `{slug}`")

        if st.session_state["replace_pending"]:
            _rp = st.session_state["replace_payload"]
            st.warning(
                f"**'{slug}'** is already loaded ({_rp.get('rows', '?')} chunks). "
                f"Replace it with this file?"
            )
            _c1, _c2 = st.columns(2)
            if _c1.button("Replace", type="primary", use_container_width=True):
                st.session_state["replace_pending"] = False
                _payload = st.session_state["replace_payload"]
                st.session_state["replace_payload"] = None
                _run_ingest(_payload["slug"], _payload["pdf_b64"])
            if _c2.button("Cancel", use_container_width=True):
                st.session_state["replace_pending"] = False
                st.session_state["replace_payload"] = None

        elif st.button("Ingest into IRIS", type="primary", use_container_width=True):
            pdf_b64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
            pdf_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()

            # Pre-check: find out what /ingest would do before committing.
            try:
                chk = iris_get("/ingest/check", params={"slug": slug, "hash": pdf_hash})
                action = chk.json().get("action", "new") if chk.status_code == 200 else "new"
            except requests.RequestException:
                action = "new"

            if action == "replace":
                st.session_state["replace_pending"] = True
                st.session_state["replace_payload"] = {
                    "slug": slug,
                    "pdf_b64": pdf_b64,
                    "rows": chk.json().get("rows", "?"),
                }
                st.rerun()
            else:
                _run_ingest(slug, pdf_b64)

    # ── Query context ────────────────────────────────────────────────────────
    st.markdown("<div class='side-section'>Query context</div>", unsafe_allow_html=True)

    pdf_options = fetch_list("/pdfs", "pdfs")
    choices = [""] + pdf_options
    default_slug = st.session_state.get("slug", "")
    idx = choices.index(default_slug) if default_slug in choices else 0
    pdf = st.selectbox("Document", choices, index=idx)
    if not pdf_options:
        st.caption("No documents loaded yet — ingest a PDF above.")

    patient_options = fetch_list("/patients", "patients", params={"pdf": pdf}) if pdf else []
    patient = st.selectbox("Patient (optional)", [""] + patient_options, index=0)

    visit_date = st.text_input("Visit date (optional)", placeholder="YYYY / YYYY-MM / YYYY-MM-DD")
    resource = st.selectbox(
        "Preferred guideline source",
        ["ACE", "NICE", "NDF", "HSA", "FDA", "NIH", "CDC"],
        index=1,
        help="The agent may choose a different source if more appropriate.",
    )
    top_k = st.selectbox("Top k results", list(range(1, 11)), index=4)

    # ── Settings ─────────────────────────────────────────────────────────────
    st.markdown("<div class='side-section'>Settings</div>", unsafe_allow_html=True)
    with st.expander("Duplicate detection", expanded=False):
        _modes = ["Slug", "Content"]
        _cur_mode = fetch_value("/dedup", "mode", default="Slug")
        _sel_mode = st.radio(
            "When is an uploaded PDF a duplicate?",
            _modes,
            index=_modes.index(_cur_mode) if _cur_mode in _modes else 0,
            help=(
                "**Slug** — identity is the filename. A renamed-but-identical PDF "
                "loads as new; re-using a name is blocked.\n\n"
                "**Content** — identity is the file's bytes (SHA-256). Identical "
                "content under a new name is blocked; a *changed* file under an "
                "existing name re-loads and replaces it."
            ),
        )
        if _sel_mode != _cur_mode:
            try:
                iris_post("/dedup", {"mode": _sel_mode}, timeout=15)
                st.caption(f"Dedup mode set to **{_sel_mode}**.")
            except requests.RequestException as e:
                st.error(f"Couldn't set dedup mode: {e}")

    with st.expander("Diagnostics", expanded=False):
        if st.button("Check IRIS health", use_container_width=True):
            try:
                r = iris_get("/health")
                (st.success if r.status_code == 200 else st.error)(f"{r.status_code}: {r.text}")
            except requests.RequestException as e:
                st.error(str(e))
        if AUTOSTART_SIDECAR:
            _sidecar_status = ensure_sidecar()
            st.caption(f"Extractor sidecar @ {SIDECAR_HOST}:{SIDECAR_PORT} — {_sidecar_status}")


# ── Main: header + conversation ──────────────────────────────────────────────
st.markdown(
    """
    <div class="app-header">
      <div class="app-header-title">Clinical Evidence Assistant</div>
      <div class="app-header-sub">Grounded answers from patient records and clinical guidelines.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

_meta_l, _meta_r = st.columns([3, 1])
_meta_l.markdown(
    f"<div class='conv-meta'><span class='conv-dot'></span>"
    f"Session {st.session_state['thread_id'][:8]} · {len(st.session_state['messages']) // 2} exchanges</div>",
    unsafe_allow_html=True,
)
with _meta_r:
    if st.button("New conversation", use_container_width=True):
        st.session_state["thread_id"] = str(uuid4())
        st.session_state["messages"] = []
        st.rerun()

st.divider()

# Render the conversation so far.
if st.session_state["messages"]:
    for _msg in st.session_state["messages"]:
        _render_message(_msg)
else:
    st.markdown(
        """
        <div class="ce-empty">
          <h4>Start a conversation</h4>
          Pick a document in the sidebar, then ask a clinical question. Follow-up
          questions keep the context of this conversation until you start a new one.
          <div style="margin-top:.8rem">
            <span class="ce-chip">Summarise this patient's recent visits</span>
            <span class="ce-chip">What does NICE recommend for their HbA1c?</span>
            <span class="ce-chip">Any medication interactions to flag?</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Chat input (pinned to the bottom) ────────────────────────────────────────
prompt = st.chat_input("Ask a clinical question about the selected document…")

if prompt:
    if not prompt.strip():
        st.toast("Please enter a question.", icon="⚠️")
    elif not pdf.strip():
        st.toast("Select a document in the sidebar before asking.", icon="⚠️")
    else:
        user_msg = {"role": "user", "content": prompt}
        st.session_state["messages"].append(user_msg)
        _render_message(user_msg)

        payload = {
            "question": prompt,
            "thread_id": st.session_state["thread_id"],
            "pdf": pdf,
            "patient": patient or "",
            "visit_date": visit_date or "",
            "resource": resource or "",
            "top_k": top_k,
        }

        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            with st.spinner("Reasoning over records and guidelines…"):
                try:
                    resp = agent_post("/query", payload, timeout=180)
                except requests.RequestException as e:
                    resp = None
                    err = f"Request to agent service failed: {e}"

            if resp is None:
                st.error(err)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": f"⚠️ {err}", "tool_log": []}
                )
            elif resp.status_code != 200:
                err = f"Query failed ({resp.status_code}): {resp.text}"
                st.error(err)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": f"⚠️ {err}", "tool_log": []}
                )
            else:
                data = resp.json()
                answer = data.get("answer", "")
                tool_log = data.get("tool_log", [])
                st.markdown(answer)
                _render_tool_log(tool_log)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": answer, "tool_log": tool_log}
                )
