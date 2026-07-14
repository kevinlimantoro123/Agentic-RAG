# Agentic Clinical RAG on InterSystems IRIS

An **agentic** Retrieval-Augmented Generation system for clinical documents, built on
**InterSystems IRIS Interoperability**. Upload a clinical PDF and IRIS orchestrates the
pipeline — extract → clean → chunk → embed into an IRIS vector store (`Embedding.Clinical`,
OpenAI 1536-dim + **HNSW** index) — then answer clinical questions with an agent that
decides *which tools to call and when*, looping until it can answer with citations.

IRIS owns the **ingest and retrieval layer**: a REST front door dispatches to business
services → business processes → business operations, and holds the vector store. The
**agentic query loop runs out-of-IRIS** in a LangGraph agent service (`agent/`, see
[`agent/README.md`](agent/README.md)) that calls IRIS's `/retrieve` for HNSW vector search.
The other non-IRIS pieces are a thin Streamlit UI (chat with multi-turn history) and an
out-of-process FastAPI "sidecar" that isolates the heavy PDF-extraction libraries.

> For the IRIS-internal design (classes, message flow, the sidecar contract), see
> [`src/RAG2026/README.md`](src/RAG2026/README.md).

---

## Architecture

```
  ┌───────────────────────────────┐        ┌───────────────────────────────┐
  │    Streamlit UI (frontend/)   │        │  Extractor sidecar (sidecar/) │
  │  upload PDF · chat w/ history │        │  FastAPI; unstructured + OCR  │
  └──────┬─────────────────┬──────┘        └────────────────▲──────────────┘
         │ ingest,         │ POST /query                    │ HTTP /prepare
         │ pdfs, dedup     ▼                                │
         │ (REST)  ┌───────────────────────────────┐        │
         │         │  LangGraph agent  (agent/)    │        │
         │         │  FastAPI :8001 — ReAct loop,  │        │
         │         │  tools, multi-turn memory     │        │
         │         └───────────────┬───────────────┘        │
         │                         │ POST /retrieve         │
         ▼                         ▼                        │
   ┌──────────────────────────────────────────────────────┼───────────────┐
   │                  InterSystems IRIS (RAG2026)          │               │
   │   REST.Dispatch ──► BS ──► BP ──────────────► BO ─────┘               │
   │   Retrieve:  Retrieve Service → Retrieve Operation → Embedding.Clinical│
   │   Ingest:    Ingest Service   → Ingest Process → { Prepare, Load } Op  │
   │   Embedding.Clinical  (vectors + HNSW index)                          │
   │   %Embedding.Config   → OpenAI text-embedding-3-small (1536-dim)      │
   └────────────────────────────────────────────────────────────────────────┘
```

- **The agentic query loop** (LLM ↔ tools, guideline search) runs in the **LangGraph agent
  service** (`agent/`), out of IRIS; it calls IRIS `/retrieve` for HNSW vector search.
- **Heavy Python** (`unstructured`/torch/OCR) runs **out-of-process** in the sidecar that
  `Prepare Operation` calls over HTTP — a crash there can never take down IRIS.
- **IRIS** owns ingest orchestration, the vector store, and server-side embedding
  generation (`%Embedding.Config`).

---

## Components (IRIS production `RAG2026.Production`)

| Item (production name) | Class | Role |
|---|---|---|
| Retrieve Service | `RAG2026.BS.RetrieveService` | REST `/retrieve` → Retrieve Operation (called by the agent) |
| Retrieve Operation | `RAG2026.BO.RetrieveOperation` | HNSW search over `Embedding.Clinical` |
| Ingest Service | `RAG2026.BS.IngestService` | REST → Ingest Process |
| Ingest Process | `RAG2026.BP.IngestProcess` | Prepare → Load |
| Prepare Operation | `RAG2026.BO.PrepareOperation` | calls the extractor sidecar |
| Load Operation | `RAG2026.BO.LoadOperation` | loads `chunks.json` → `Embedding.Clinical` |

Plus: `RAG2026.REST.Dispatch` (HTTP front door), `RAG2026.Setup` (one-shot env setup),
`RAG2026.Msg.*` (typed messages), and `RAG2026.Data.IngestJob` (async ingest job tracking).

> **The query path moved out of IRIS.** The agentic loop now runs in the LangGraph agent
> service (`agent/`). `Query Service`, `Agent Process`, `LLM Operation`, and
> `Guideline Operation` are left on disk but are **no longer exercised** — the agent runs the
> loop itself and only calls `Retrieve Service` for vector search. See
> [`agent/README.md`](agent/README.md) for the full what-moved / what-stayed mapping.

---

## Tech stack

| Layer | Technology |
|---|---|
| Ingest / retrieval orchestration | InterSystems IRIS Interoperability (BS/BP/BO) |
| Agent runtime | LangGraph `create_react_agent` + `langchain-openai` (`agent/`, out of IRIS) |
| LLM | OpenAI `gpt-4o` (tool calling), driven by LangGraph |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim), generated **server-side by IRIS** |
| Vector store | `Embedding.Clinical` + HNSW index |
| Web search | Tavily (`langchain-tavily`), a tool in the agent |
| PDF processing | `unstructured`, Tesseract OCR, Poppler (in the sidecar) |
| Chunking | LangChain text splitters + `tiktoken` |
| UI | Streamlit — REST client, chat with multi-turn history |

---

## Prerequisites

- An **InterSystems IRIS** instance with Interoperability (2024.1+ for HNSW).
- **Python 3.10+** for the agent, sidecar, and frontend (a venv in the repo root).
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

### 6. Python venv for the agent, sidecar + frontend (repo root)
```bash
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1   |  *nix: source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` in the repo root with the keys the **agent service** reads (the LLM and
guideline-search keys are no longer taken from IRIS credentials):
```bash
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

### 7. Start the production
Interoperability → Configure → Production → `RAG2026.Production` → **Start**
(set Auto-Start on a server).

---

## Running the app

The query path runs in the **LangGraph agent service**, so start it alongside Streamlit.
The Streamlit frontend still **auto-starts the extractor sidecar** (set `AUTOSTART_SIDECAR=0`
to manage it yourself). From the repo root, in the venv:

```bash
# 1) LangGraph agent service — serves POST /query on :8001
#    Needs OPENAI_API_KEY and TAVILY_API_KEY in .env (see Configuration reference).
uvicorn agent.server:app --host 127.0.0.1 --port 8001

# 2) Streamlit frontend — in a second terminal
streamlit run frontend/app.py
```

Open <http://localhost:8501>. (Run the agent with a **single** uvicorn worker — conversation
memory is in-process and isn't shared across workers.)

1. **Upload a clinical PDF.** IRIS queues an async ingest job (extract → clean → chunk →
   load), the UI polls for progress, and on completion shows the chunk count. **Duplicate
   uploads are detected by slug (the PDF filename stem)** and skipped with a message.
2. **Set query context** in the sidebar (document, optional patient, optional visit date,
   preferred guideline source, top-k).
3. **Chat with the agent.** The conversation is shown in full and **keeps context across
   follow-up questions** (multi-turn memory, keyed per session); click **New conversation**
   to reset the chat window and start a fresh thread. Expand **Retrieval & sources** under an
   answer to see which tools ran and what each returned.

To run the extractor sidecar manually instead of auto-start:
```bash
python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800
```

---

## REST API

### IRIS (`/csp/rag2026`)

```
GET  /health                              -> {"status":"ok"}
GET  /pdfs                                -> {"pdfs":[...]}        distinct loaded slugs
GET  /patients?pdf=<slug>                 -> {"patients":[...]}    distinct patients
POST /retrieve {"query","pdf","patient","visit_date","top_k"}  -> [{label,date,text}]
POST /ingest   {"slug","pdf_base64"}      -> {"job_id","status"}  | {"status":"Duplicate",...}
GET  /ingest/status?id=<jobId>            -> {status, slug, rows_inserted, error?}
```

`/retrieve` is called by the agent service, not the browser. `/ingest` is **asynchronous**:
it queues a `RAG2026.Data.IngestJob`, runs the work in a background process (so the HTTP
request returns immediately and never trips the Web Gateway timeout on long extractions),
and the client polls `/ingest/status`.

### LangGraph agent (`http://localhost:8001`)

```
GET  /health                              -> {"status":"ok"}
POST /query    {"question","thread_id","pdf","patient","visit_date","resource","top_k"}
               -> {"answer","tool_log":[{tool,args,result}]}
```

`thread_id` keys the agent's **multi-turn memory**: reuse it for follow-up questions in the
same conversation, and send a new one (the UI's **New conversation** button) to start fresh.
Memory is in-process (`MemorySaver`) — it is lost on restart and not shared across workers.

---

## How it works

### The agentic loop (LangGraph agent, `agent/graph.py`)
A LangGraph `create_react_agent` drives the loop. Each turn, the LLM (`gpt-4o`) is given two
tools and may call `retrieve_patient_records` (IRIS HNSW vector search over `/retrieve`),
`guideline_search` (Tavily over NICE/FDA/CDC/ACE/NDF/HSA/NIH), both, or neither — then sees
the results and decides to refine, call again, or answer. Loops up to `AGENT_MAX_ITERATIONS`
(default 10). Conversation history is persisted per `thread_id` by a `MemorySaver`
checkpointer, so follow-up questions carry context.

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
├── agent/                    # LangGraph agent service (agentic query loop, out of IRIS)
│   ├── server.py             # FastAPI: GET /health, POST /query  (uvicorn :8001)
│   ├── graph.py              # create_react_agent + MemorySaver (multi-turn memory)
│   ├── tools.py              # retrieve_patient_records (IRIS /retrieve) + guideline_search
│   ├── llm.py  config.py     # ChatOpenAI + env config
│   └── README.md             # what moved out of IRIS and what stayed
├── sidecar/
│   └── extract_service.py    # FastAPI extractor (heavy Python, out-of-process)
├── pipeline/                 # extract → clean → chunk (wrapped by the sidecar)
│   ├── extractor.py          # PDF → text/tables/images (unstructured + OCR)
│   ├── cleaner.py            # boilerplate removal → organized Markdown
│   └── chunker.py            # heading-aware chunking + patient/date metadata
├── frontend/
│   └── app.py                # Streamlit UI (REST client; chat with multi-turn history)
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
| `AGENT_URL` | Where the frontend sends `/query` (the agent service) | `http://localhost:8001` |
| `SIDECAR_HOST` / `SIDECAR_PORT` | Where the sidecar listens | `127.0.0.1` / `8800` |
| `SIDECAR_STRATEGY` | `unstructured` extraction strategy | `fast` (`hi_res` for OCR-heavy PDFs) |
| `AUTOSTART_SIDECAR` | Let Streamlit launch the sidecar | `1` |

### LangGraph agent (`.env`, read by `agent/`)

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | Key for the agent's `ChatOpenAI` (**required**) | — |
| `OPENAI_MODEL` | Chat model | `gpt-4o` |
| `TAVILY_API_KEY` | Key for `guideline_search` (**required**) | — |
| `AGENT_MAX_ITERATIONS` | LLM ↔ tool iterations per turn | `10` |
| `AGENT_DEFAULT_TOP_K` | Default retrieval top-k | `5` |
| `IRIS_REST_URL` / `IRIS_USER` / `IRIS_PASSWORD` | Base URL + auth for IRIS `/retrieve` | same as frontend |

The agent's `OPENAI_API_KEY` / `TAVILY_API_KEY` live in the **process env / `.env`**, not IRIS
credentials. IRIS still uses its own stored OpenAI key for server-side embedding. See
[`agent/README.md`](agent/README.md) for the full list.

### IRIS tunables (production SETTINGS)

| Setting | Host | Default |
|---|---|---|
| `EmbeddingConfig` | Retrieve / Load Operation | `openai-embedding-config` |
| `SidecarURL` / `WorkDir` / `RequestTimeout` | Prepare Operation | `…:8800/prepare` / `/opt/app/data/` / `3600` |

The old query-path settings (`MaxIterations` / `DefaultTopK` on Agent Process, `Model` on LLM
Operation) are **superseded** by the agent's `AGENT_MAX_ITERATIONS` / `AGENT_DEFAULT_TOP_K` /
`OPENAI_MODEL` env vars. IRIS's `OpenAIKey` credential is still used for **server-side
embedding**; the agent's LLM and Tavily keys come from `.env`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Request to agent service failed` when asking a question | The LangGraph agent isn't running. Start it: `uvicorn agent.server:app --host 127.0.0.1 --port 8001` (check `AGENT_URL`). |
| Agent answers but guideline/LLM calls fail | Missing `OPENAI_API_KEY` / `TAVILY_API_KEY` in the repo-root `.env` that the agent process reads. |
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
