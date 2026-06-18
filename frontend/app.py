import streamlit as st
from rag_tool.test_rag import retrieve_text_chunks, guideline_search, answer_question, reset
from pathlib import Path
from pipeline.precheck import ensure_meta_table, check_duplicate, record_metadata
from pipeline.extractor import Extractor
from pipeline.cleaner import organize_and_clean_by_section
from pipeline.chunker import main as chunk_markdown
from pipeline.loader import load_chunks_to_iris
from pipeline.utils import get_patient_list, get_pdf_list

# Page config & CSS
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

# --- STEP 1: PDF upload + OCR/chunking/load into IRIS ---
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

    # ─── Pre‐check for duplicates ─────────────────────────
    ensure_meta_table()
    with st.spinner("🔍 Checking if this PDF was already processed…"):
        is_dup, uploaded_at, file_hash, size_bytes, page_count = check_duplicate(pdf_path, slug)

    # ─── Pre-check for duplicates ─────────────────────────────
    override = st.checkbox("⚠️ Force re-upload even if already processed")
    ensure_meta_table()
    with st.spinner("🔍 Checking for prior load…"):
        is_dup, uploaded_at, file_hash, size_bytes, page_count = check_duplicate(pdf_path, slug)

    if is_dup and not override:
        st.warning(f"ℹ️ PDF “{slug}” was already loaded on {uploaded_at:%Y-%m-%d %H:%M}.")
        st.info("Tick **Force re-upload** above to process it again.")
        st.stop()

    # create a progress bar (0–100)
    prog = st.progress(0)

    # 1️⃣ Extract
    with st.spinner("🔍 Extracting text, images, tables…"):
        extractor = Extractor(output_root="data")
        stats = extractor.extract(str(pdf_path))
    st.write("Extraction stats:", stats)
    prog.progress(25)

    # 2️⃣ Clean → Markdown
    with st.spinner("🧹 Cleaning & organizing into Markdown…"):
        organize_and_clean_by_section("data", slug)
    md_file = out_dir / "organized_cleaned_document.md"
    st.write("Cleaned Markdown at:", md_file)
    prog.progress(50)

    # 3️⃣ Chunk → JSON
    with st.spinner("✂️ Splitting into chunks…"):
        chunk_markdown(slug)
    chunks_json = out_dir / "chunks.json"
    st.write("Chunks JSON at:", chunks_json)
    prog.progress(75)

    # 4️⃣ Load into IRIS
    with st.spinner("Loading chunks into IRIS…"):
        inserted = load_chunks_to_iris(slug, str(chunks_json))
    st.success(f"✅ Loaded {inserted} new rows into Embedding.{slug}")
    prog.progress(100)

    # 5️⃣ Record metadata for next time
    if inserted > 0:
        record_metadata(slug, file_hash, size_bytes, page_count)

    st.success("🎉 PDF successfully processed and loaded!")

# Sidebar filters
with st.sidebar:
    st.header("🩺 RAG Controls")
    # ← drop it in here
    if st.button("Reset Database"):
        with st.spinner("🔄 Resetting Embedding tables…"):
            reset()
        st.success("✅ Database reset successfully.")
    st.header("🩺 RAG Query")
    slug = st.session_state["slug"]
    pdfs = [""] + get_pdf_list()
    pdf = st.selectbox("PDF to query", pdfs, index=0)
    patients = [""] + get_patient_list(pdf)
    patient  = st.selectbox("Patient name (optional)", patients, index=0)
    visit_date = st.text_input("Visit date (YYYY or YYYY-MM or YYYY-MM-DD) (optional)")
    resource = st.selectbox("Guideline source", list(
        ["ACE","NICE","NDF","HSA","FDA","NIH","CDC"]
    ), index=1)
    top_k = st.selectbox("Top k results", list([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), index=0)


st.title("🩺 Clinical RAG + Web Search Agent")
question = st.text_input("Enter your clinical question:")


if st.button("Run"):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Retrieving context…"):
            chunks = retrieve_text_chunks(
                question, pdf, top_k=top_k, patient=patient or None, visit_date=visit_date or None
            )
            guides = guideline_search(question, resource, max_results=3)
        # if not chunks:
        #     st.error("❌ No patient data found for that query/filters.")
        # else:
            # -- Patient Data Section --
            with st.expander("🗄️ Patient Data (Database)"):
                for c in chunks:
                    label = c.get('label', '')
                    date = c.get('date', '')
                    text = c.get('text', '')
                    st.markdown(f"**[{label}|{date}]** {text}")

            # -- Guideline Snippets Section --
            with st.expander("🌐 Guideline Snippets (Web Sources)"):
                if not guides:
                    st.write("_No guideline snippets found. Try a different resource or broaden your query/domain filter._")
                else:
                    for g in guides:
                        label = g.get('label', '')
                        source = g.get('source') or 'n/a'
                        text = g.get('text', '')
                        st.markdown(f"**[{label}|{source}]** {text}")
            # --- ANSWER ---
            with st.spinner("Generating answer…"):
                answer = answer_question(question, chunks, guides)

            st.markdown("### 💬 Answer")
            st.markdown(answer)
