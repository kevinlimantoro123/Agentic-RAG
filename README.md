# Agentic Clinical RAG on InterSystems IRIS

An **agentic** Retrieval-Augmented Generation system for clinical documents, built on
**InterSystems IRIS Interoperability**. Upload a clinical PDF and IRIS orchestrates the
pipeline — extract → clean → chunk → embed into an IRIS vector store (`Embedding.Clinical`,
OpenAI 1536-dim + **HNSW** index) — then answer clinical questions with an agent that
decides *which tools to call and when*, looping until it can answer with citations.

IRIS is the **orchestration layer**: a REST front door dispatches to business services →
business processes → business operations. The only non-IRIS pieces are a thin Streamlit UI
and an out-of-process FastAPI "sidecar" that isolates the heavy PDF-extraction libraries.

> For the IRIS-internal design (classes, message flow, the sidecar contract), see
> [`src/RAG2026/README.md`](src/RAG2026/README.md).

---

## Architecture

```
        ┌─────────────────────────────┐        ┌──────────────────────────────┐
        │   Streamlit UI (frontend/)  │        │  Extractor sidecar (sidecar/) │
        │  upload PDF · ask questions │        │  FastAPI; unstructured + OCR  │
        └──────────────┬──────────────┘        └───────────────▲──────────────┘
                       │ HTTP (REST)                            │ HTTP /prepare
                       ▼                                        │
   ┌──────────────────────────────────────────────────────────┼───────────────┐
   │                       InterSystems IRIS (RAG2026)         │               │
   │                                                            │               │
   │   REST.Dispatch ──► BS ──► BP ──────────────► BO ──────────┘               │
   │                                                                            │
   │   Query:   Query Service → Agent Process → { LLM, Retrieve, Guideline } Op │
   │   Ingest:  Ingest Service → Ingest Process → { Prepare, Load } Op          │
   │                                                                            │
   │   Embedding.Clinical  (vectors + HNSW index)                               │
   │   %Embedding.Config   → OpenAI text-embedding-3-small (1536-dim)           │
   └────────────────────────────────────────────────────────────────────────────┘
```

- **Light Python** (openai, langchain_tavily, SQL) runs **embedded in-process** in IRIS.
- **Heavy Python** (`unstructured`/torch/OCR) runs **out-of-process** in the sidecar that
  `Prepare Operation` calls over HTTP — a crash there can never take down IRIS.

---

## Components (IRIS production `RAG2026.Production`)

| Item (production name) | Class | Role |
|---|---|---|
| Query Service | `RAG2026.BS.QueryService` | REST → Agent Process |
| Agent Process | `RAG2026.BP.AgentProcess` | the agentic loop (LLM ↔ tools) |
| LLM Operation | `RAG2026.BO.LLMOperation` | one OpenAI chat call (tools / tool_calls) |
| Retrieve Operation | `RAG2026.BO.RetrieveOperation` | HNSW search over `Embedding.Clinical` |
| Guideline Operation | `RAG2026.BO.GuidelineOperation` | Tavily authoritative-domain search |
| Ingest Service | `RAG2026.BS.IngestService` | REST → Ingest Process |
| Ingest Process | `RAG2026.BP.IngestProcess` | Prepare → Load |
| Prepare Operation | `RAG2026.BO.PrepareOperation` | calls the extractor sidecar |
| Load Operation | `RAG2026.BO.LoadOperation` | loads `chunks.json` → `Embedding.Clinical` |

Plus: `RAG2026.REST.Dispatch` (HTTP front door), `RAG2026.Setup` (one-shot env setup),
`RAG2026.Msg.*` (typed messages), and `RAG2026.Data.IngestJob` (async ingest job tracking).

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | InterSystems IRIS Interoperability (BS/BP/BO) |
| LLM / agent | OpenAI `gpt-4o` (function calling), called from IRIS embedded Python |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim), generated **server-side by IRIS** |
| Vector store | `Embedding.Clinical` + HNSW index |
| Web search | Tavily (`langchain-tavily`) |
| PDF processing | `unstructured`, Tesseract OCR, Poppler (in the sidecar) |
| Chunking | LangChain text splitters + `tiktoken` |
| UI | Streamlit (REST client only) |

---

## Prerequisites

- An **InterSystems IRIS** instance with Interoperability (2024.1+ for HNSW).
- **Python 3.10+** for the sidecar and frontend (a venv in the repo root).
- **Tesseract OCR** + **Poppler** on the sidecar host (for `hi_res` extraction).
- **API keys**: OpenAI and Tavily.

---

## Setup

### 1. IRIS namespace + interoperability (in `%SYS`)
```objectscript
zn "%SYS"  do ##class(%Library.EnsembleMgr).EnableNamespace("RAG2026")
```

### 2. Load the classes (in `RAG2026`)
```objectscript
zn "RAG2026"  do $SYSTEM.OBJ.LoadDir("/path/to/Agentic-RAG/src/RAG2026","ck",,1)
```

### 3. Install embedded-Python deps into the IRIS instance (light only)
```
<iris-install>/bin/irispython -m pip install openai langchain-tavily requests
```

### 4. One-shot setup (in `RAG2026`)
Creates the `llm_ssl` TLS config, the `OpenAIKey`/`TavilyKey` interop credentials, and the
`openai-embedding-config` embedding config:
```objectscript
do ##class(RAG2026.Setup).Init("sk-...openai...","tvly-...tavily...")
```

### 5. Register the REST web application
Management Portal → System Administration → Security → Applications → Web Applications →
**New**: name `/csp/rag2026`, namespace `RAG2026`, Dispatch Class `RAG2026.REST.Dispatch`,
enable an auth method.

### 6. Python venv for the sidecar + frontend (repo root)
```bash
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1   |  *nix: source venv/bin/activate
pip install -r requirements.txt
```

### 7. Start the production
Interoperability → Configure → Production → `RAG2026.Production` → **Start**
(set Auto-Start on a server).

---

## Running the app

The Streamlit frontend **auto-starts the sidecar** (set `AUTOSTART_SIDECAR=0` to manage it
yourself). From the repo root, in the venv:

```bash
streamlit run frontend/app.py
```

Open <http://localhost:8501>.

1. **Upload a clinical PDF.** IRIS queues an async ingest job (extract → clean → chunk →
   load), the UI polls for progress, and on completion shows the chunk count. **Duplicate
   uploads are detected by slug (the PDF filename stem)** and skipped with a message.
2. **Set query filters** in the sidebar (PDF, optional patient, optional visit date,
   preferred guideline source, top-k).
3. **Ask a question.** Expand the agent steps to see which tools were chosen and what each
   returned.

To run the sidecar manually instead of auto-start:
```bash
python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800
```

---

## REST API (`/csp/rag2026`)

```
GET  /health                              -> {"status":"ok"}
GET  /pdfs                                -> {"pdfs":[...]}        distinct loaded slugs
GET  /patients?pdf=<slug>                 -> {"patients":[...]}    distinct patients
POST /query    {"question","pdf","patient","visit_date","resource","top_k"}
POST /ingest   {"slug","pdf_base64"}      -> {"job_id","status"}  | {"status":"Duplicate",...}
GET  /ingest/status?id=<jobId>            -> {status, slug, rows_inserted, error?}
```

`/ingest` is **asynchronous**: it queues a `RAG2026.Data.IngestJob`, runs the work in a
background process (so the HTTP request returns immediately and never trips the Web Gateway
timeout on long extractions), and the client polls `/ingest/status`.

---

## How it works

### The agentic loop (`Agent Process`)
Each turn, the LLM (`gpt-4o`) is given two tools with `tool_choice="auto"` and may call
`retrieve_patient_records` (HNSW vector search), `guideline_search` (Tavily over
NICE/FDA/CDC/ACE/NDF/HSA/NIH), both, or neither — then sees the results and decides to
refine, call again, or answer. Loops up to `MaxIterations` (default 10).

### HNSW vector search (`Load Operation` / `Retrieve Operation`)
On first load, `Load Operation` creates:
```sql
CREATE INDEX HNSWIndex ON TABLE Embedding.Clinical (DescriptionEmbedding)
AS HNSW(M=32, efConstruction=100, Distance='DotProduct')
```
Retrieval issues a `TOP-k ... ORDER BY VECTOR_DOT_PRODUCT(...) DESC` query so the optimizer
is eligible to use the HNSW index; embeddings are generated server-side by IRIS.

> **HNSW at small scale:** the cost-based optimizer only chooses the approximate index when
> the table is large enough to beat an exact scan — with a few dozen rows it correctly does
> an exact scan. Check with `EXPLAIN`.

---

## Project structure

```
Agentic-RAG/
├── src/RAG2026/              # the app: IRIS interoperability classes
│   ├── Production.cls        # production definition
│   ├── Setup.cls             # one-shot env setup (TLS, credentials, embedding config)
│   ├── REST/Dispatch.cls     # HTTP front door (%CSP.REST)
│   ├── BS/  BP/  BO/  Msg/   # services, processes, operations, messages
│   └── README.md             # IRIS-internal design details
├── sidecar/
│   └── extract_service.py    # FastAPI extractor (heavy Python, out-of-process)
├── pipeline/                 # extract → clean → chunk (wrapped by the sidecar)
│   ├── extractor.py          # PDF → text/tables/images (unstructured + OCR)
│   ├── cleaner.py            # boilerplate removal → organized Markdown
│   └── chunker.py            # heading-aware chunking + patient/date metadata
├── frontend/
│   └── app.py                # Streamlit UI (REST client only)
├── data/                     # work dir: <slug>/<slug>.pdf and <slug>/chunks.json
├── requirements.txt
└── .env                      # frontend + sidecar config (not committed)
```

---

## Configuration reference

### Frontend / sidecar (`.env`, read by `frontend/app.py`)

| Variable | Description | Default |
|---|---|---|
| `IRIS_REST_URL` | Base URL of the IRIS REST app | `http://localhost:52773/csp/rag2026` |
| `IRIS_USER` / `IRIS_PASSWORD` | REST auth | `SuperUser` / `SYS` |
| `SIDECAR_HOST` / `SIDECAR_PORT` | Where the sidecar listens | `127.0.0.1` / `8800` |
| `SIDECAR_STRATEGY` | `unstructured` extraction strategy | `fast` (`hi_res` for OCR-heavy PDFs) |
| `AUTOSTART_SIDECAR` | Let Streamlit launch the sidecar | `1` |

### IRIS tunables (production SETTINGS)

| Setting | Host | Default |
|---|---|---|
| `MaxIterations` / `DefaultTopK` | Agent Process | 10 / 5 |
| `Model` | LLM Operation | `gpt-4o` |
| `EmbeddingConfig` | Retrieve / Load Operation | `openai-embedding-config` |
| `SidecarURL` / `WorkDir` / `RequestTimeout` | Prepare Operation | `…:8800/prepare` / `/opt/app/data/` / `3600` |

Secrets (`OpenAIKey`, `TavilyKey`) live in **IRIS interop credentials**, not `.env`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Ingest hangs / Web Gateway timeout on a big PDF | Raise `RequestTimeout` on Prepare Operation; ingest is async so the HTTP call itself returns fast. |
| `Error occurring during INSERT in 'Embedding.Clinical'` | Server-side embedding call failed — verify the `llm_ssl` SSL config exists, the `OpenAIKey` credential is valid, and the VM can reach `api.openai.com` (incl. any proxy). |
| `Embedding config 'openai-embedding-config' ... not defined` | Run `RAG2026.Setup.Init(...)` in the `RAG2026` namespace. |
| `bind on address ... 8800` | The sidecar is already running (Streamlit auto-started it). Don't start a second one, or set `AUTOSTART_SIDECAR=0`. |
| Re-uploading the same PDF shows "Duplicate" | Expected — detection is by slug (filename stem). Rename the file to ingest it as a new document. |
| `TesseractNotFoundError` / Poppler errors | Install Tesseract + Poppler on the sidecar host and ensure they're on PATH. |

---

## Notes & caveats

- **`openai-embedding-config` is a label, not the model.** It points at OpenAI
  `text-embedding-3-small`; the name is kept for code compatibility.
- **Duplicate detection is by filename (slug), not content.** A renamed-but-identical PDF
  ingests as a new document.
- **Clinical text is sent to OpenAI** for embedding and answering. Use only with data you're
  authorized to send to a third-party API.
