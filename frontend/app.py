import streamlit as st
from pathlib import Path
from rag_tool.agent import run_agent_streaming
from rag_tool.test_rag import reset
from pipeline.precheck import ensure_meta_table, check_duplicate, record_metadata
from pipeline.extractor import Extractor
from pipeline.cleaner import organize_and_clean_by_section
from pipeline.chunker import main as chunk_markdown
from pipeline.loader import load_chunks_to_iris
from pipeline.utils import get_patient_list, get_pdf_list

st.set_page_config(page_title="Clinical AI Assistant", layout="wide")
st.title("📄→🧠 Clinical PDF → RAG Pipeline")
st.markdown(
    """
    <style>
      .stExpanderHeader { font-size: 1.1em; font-weight: bold; }
      .citation { color: #555; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True
)

if "slug" not in st.session_state:
    st.session_state["slug"] = ""

# ── STEP 1: PDF upload ──────────────────────────────────────────────────────
uploaded = st.file_uploader("Upload clinical PDF", type="pdf")
if uploaded:
    slug    = Path(uploaded.name).stem
    out_dir = Path("data") / slug
    out_dir.mkdir(exist_ok=True, parents=True)
    st.session_state["slug"] = slug
    pdf_path = out_dir / uploaded.name
    with open(pdf_path, "wb") as f:
        f.write(uploaded.getbuffer())
    st.success(f"Saved PDF: {pdf_path}")

    ensure_meta_table()
    override = st.checkbox("⚠️ Force re-upload even if already processed")
    with st.spinner("🔍 Checking for prior load…"):
        is_dup, uploaded_at, file_hash, size_bytes, page_count = check_duplicate(pdf_path, slug)

    if is_dup and not override:
        st.warning(f"ℹ️ PDF '{slug}' was already loaded on {uploaded_at:%Y-%m-%d %H:%M}.")
        st.info("Tick **Force re-upload** above to process it again.")
        st.stop()

    prog = st.progress(0)

    with st.spinner("🔍 Extracting text, images, tables…"):
        extractor = Extractor(output_root="data")
        stats = extractor.extract(str(pdf_path))
    st.write("Extraction stats:", stats)
    prog.progress(25)

    with st.spinner("🧹 Cleaning & organizing into Markdown…"):
        organize_and_clean_by_section("data", slug)
    md_file = out_dir / "organized_cleaned_document.md"
    st.write("Cleaned Markdown at:", md_file)
    prog.progress(50)

    with st.spinner("✂️ Splitting into chunks…"):
        chunk_markdown(slug)
    chunks_json = out_dir / "chunks.json"
    st.write("Chunks JSON at:", chunks_json)
    prog.progress(75)

    with st.spinner("⬆️ Loading chunks into IRIS…"):
        inserted = load_chunks_to_iris(slug, str(chunks_json))
    st.success(f"✅ Loaded {inserted} new rows into Embedding.Clinical")
    prog.progress(100)

    if inserted > 0:
        record_metadata(slug, file_hash, size_bytes, page_count)

    st.success("🎉 PDF successfully processed and loaded!")

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🩺 RAG Controls")
    if st.button("Reset Database"):
        with st.spinner("🔄 Resetting Embedding tables…"):
            reset()
        st.success("✅ Database reset successfully.")

    st.header("🩺 Query Filters")
    pdfs     = [""] + get_pdf_list()
    pdf      = st.selectbox("PDF to query", pdfs, index=0)
    patients = [""] + get_patient_list(pdf)
    patient  = st.selectbox("Patient name (optional)", patients, index=0)
    visit_date = st.text_input("Visit date (YYYY or YYYY-MM or YYYY-MM-DD) (optional)")
    resource   = st.selectbox(
        "Preferred guideline source",
        ["ACE", "NICE", "NDF", "HSA", "FDA", "NIH", "CDC"],
        index=1,
        help="The agent may choose a different source if more appropriate.",
    )
    top_k = st.selectbox("Top k results", list(range(1, 11)), index=4)

# ── Main query area ──────────────────────────────────────────────────────────
st.title("🤖 Agentic Clinical RAG")
st.caption(
    "GPT-4o decides which tools to call and when — it can search patient records "
    "and guidelines multiple times until it has enough context to answer."
)

question = st.text_input("Enter your clinical question:")

if st.button("Run Agent"):
    if not question.strip():
        st.warning("Please enter a question.")
    elif not pdf:
        st.warning("Please select a PDF to query from the sidebar.")
    else:
        steps_placeholder = st.empty()
        tool_events: list[dict] = []

        with st.spinner("🤖 Agent reasoning…"):
            for event in run_agent_streaming(
                question=question,
                pdf=pdf,
                patient=patient or None,
                visit_date=visit_date or None,
                top_k=top_k,
            ):
                if event["type"] == "tool_start":
                    tool_events.append(event)
                    # Live update the steps expander while agent runs
                    with steps_placeholder.container():
                        with st.expander("🔧 Agent Steps (live)", expanded=True):
                            for i, ev in enumerate(tool_events, 1):
                                st.markdown(f"**Step {i} — `{ev['tool']}`**")
                                st.json(ev.get("args", {}))

                elif event["type"] == "tool_result":
                    # Attach result to the matching start event
                    for ev in reversed(tool_events):
                        if ev["tool"] == event["tool"] and "result" not in ev:
                            ev["result"] = event["result"]
                            break

                elif event["type"] == "answer":
                    # Final answer — render complete tool log then the answer
                    steps_placeholder.empty()

                    with st.expander("🔧 Agent Tool Calls", expanded=False):
                        if not tool_events:
                            st.write("_Agent answered without calling any tools._")
                        for i, ev in enumerate(tool_events, 1):
                            st.markdown(f"**Step {i} — `{ev['tool']}`**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**Arguments**")
                                st.json(ev.get("args", {}))
                            with col2:
                                st.markdown("**Result**")
                                result = ev.get("result", [])
                                if ev["tool"] == "retrieve_patient_records":
                                    for rec in result:
                                        st.markdown(
                                            f"**[{rec.get('label', '?')}|{rec.get('date', '?')}]** "
                                            f"{rec.get('text', '')[:300]}…"
                                        )
                                elif ev["tool"] == "guideline_search":
                                    for rec in result:
                                        st.markdown(
                                            f"**[{rec.get('label', '?')}|{rec.get('source', 'n/a')}]** "
                                            f"{rec.get('text', '')[:300]}…"
                                        )
                                else:
                                    st.json(result)

                    st.markdown("### 💬 Answer")
                    st.markdown(event["text"])

                elif event["type"] == "error":
                    st.error(event["text"])
