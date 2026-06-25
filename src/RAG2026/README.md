# RAG2026 — Agentic RAG on IRIS Interoperability

IRIS is the **orchestration layer**: REST services → business processes → business
operations, with the vector store in `Embedding.Clinical` (OpenAI 1536-dim + HNSW).
This package was written from scratch (modeled on `src/Demo`, but built for the new
architecture). **Do not load `src/Demo`** — it targets the old MiniLM/linear design.

## Components

| Item (production name) | Class | Role |
|---|---|---|
| Query Service | `RAG2026.BS.QueryService` | adapterless BS, REST → Agent Process |
| Agent Process | `RAG2026.BP.AgentProcess` | the agentic loop (LLM ↔ tools) |
| LLM Operation | `RAG2026.BO.LLMOperation` | one OpenAI chat call (tools, tool_calls) |
| Retrieve Operation | `RAG2026.BO.RetrieveOperation` | HNSW search over `Embedding.Clinical` |
| Guideline Operation | `RAG2026.BO.GuidelineOperation` | Tavily authoritative-domain search |
| Ingest Service | `RAG2026.BS.IngestService` | adapterless BS, REST → Ingest Process |
| Ingest Process | `RAG2026.BP.IngestProcess` | Prepare → Load |
| Prepare Operation | `RAG2026.BO.PrepareOperation` | calls the extractor sidecar (out-of-process) |
| Load Operation | `RAG2026.BO.LoadOperation` | loads chunks.json → `Embedding.Clinical` |

Messages live in `RAG2026.Msg.*`. HTTP front door: `RAG2026.REST.Dispatch`.
Async ingest jobs are tracked in the persistent class `RAG2026.Data.IngestJob`
(status, slug, rows inserted, error).

Supporting (non-production) pieces in the repo:
- `sidecar/extract_service.py` — the FastAPI extractor sidecar (see below).
- `frontend/app.py` — a Streamlit client that talks only to the REST API.
- `pipeline/` — the extract → clean → chunk code the sidecar wraps.

## Design rule (prevents the prior segfault)

Light Python (openai, langchain_tavily, SQL) runs **embedded in-process**. Heavy
Python (`unstructured`/torch/OCR) runs **out-of-process** in the FastAPI sidecar that
`PrepareOperation` calls over HTTP — a crash there can never take down IRIS.

## Install / run (laptop and AWS VM, identical)

1. **Namespace + interop** (in `%SYS`):
   ```objectscript
   zn "%SYS"  do ##class(%Library.EnsembleMgr).EnableNamespace("RAG2026")
   ```
2. **Load classes** (in `RAG2026`):
   ```objectscript
   zn "RAG2026"  do $SYSTEM.OBJ.LoadDir("/opt/app/src/RAG2026","ck",,1)
   ```
   (Adjust the path. On a laptop it's your repo's `src/RAG2026`.)
3. **Embedded-Python deps** into the instance Python (light only):
   ```
   <install>/bin/irispython -m pip install openai langchain-tavily requests
   ```
4. **One-shot setup** (in `RAG2026`) — creates `llm_ssl`, the `OpenAIKey`/`TavilyKey`
   credentials, and the `openai-embedding-config` embedding config:
   ```objectscript
   do ##class(RAG2026.Setup).Init("sk-...openai...","tvly-...tavily...")
   ```
5. **Web application** for REST (Management Portal → System Administration → Security →
   Applications → Web Applications → New): name `/csp/rag2026`, namespace `RAG2026`,
   Dispatch Class `RAG2026.REST.Dispatch`, enable password (or your auth).
6. **Sidecar** (see below) running and reachable at `Prepare Operation`'s `SidecarURL`.
   The Streamlit frontend auto-starts it; otherwise launch it manually.
7. **Start the production**: Interoperability → Configure → Production →
   `RAG2026.Production` → Start. (Set Auto-Start for the VM.)
8. **Frontend** (optional UI), from the repo root in your Python venv:
   ```
   streamlit run frontend/app.py
   ```

## REST API

```
GET  /csp/rag2026/health                  -> {"status":"ok"}
GET  /csp/rag2026/pdfs                     -> {"pdfs":[...]}            distinct loaded slugs
GET  /csp/rag2026/patients?pdf=<slug>      -> {"patients":[...]}        distinct patients (optionally per slug)
POST /csp/rag2026/query    {"question","pdf","patient","visit_date","resource","top_k"}
POST /csp/rag2026/ingest   {"slug","pdf_base64"}
GET  /csp/rag2026/ingest/status?id=<jobId>
```

### Ingest is asynchronous

`POST /ingest` does **not** run the extraction inline (that can take minutes and would
trip the Web Gateway timeout). Instead it:

1. **Duplicate guard** — if the `slug` already has rows in `Embedding.Clinical`, it
   returns immediately without queueing:
   ```json
   {"status":"Duplicate","slug":"<slug>","rows_inserted":<n>}
   ```
   Duplicate detection is **by slug (the PDF filename stem), not by content** — a
   different filename ingests as a new document even if the contents are identical.
2. Otherwise it saves a `RAG2026.Data.IngestJob`, kicks off the work in a background
   process (`JOB`), and returns `{"job_id":"...","status":"Queued"}`.

Poll `GET /ingest/status?id=<jobId>` for progress:
```json
{"job_id":"...","slug":"...","status":"Queued|Running|Done|Error|NotFound","rows_inserted":<n>,"error":"..."}
```
The Streamlit frontend polls this endpoint and shows the duplicate / progress / result
messages.

## Extractor sidecar contract

A small FastAPI app (`sidecar/extract_service.py`) wrapping `pipeline/`:

```
GET  {host}:{port}/health    -> {"status":"ok", ...}
POST {SidecarURL}            e.g. http://127.0.0.1:8800/prepare
  body    {"slug": "...", "pdf_path": "<work_dir>/<slug>/<slug>.pdf", "work_dir": "..."}
  action  Extractor.extract -> organize_and_clean_by_section -> chunk_markdown,
          writing data/<slug>/chunks.json
  return  {"chunks_path": "<repo>/data/<slug>/chunks.json", "stats": {...}}
```

Notes:
- The PDF filename stem **must equal** the `slug` (the extractor derives its output dir
  from the stem); the sidecar rejects a mismatch with HTTP 400.
- Extraction strategy comes from the `SIDECAR_STRATEGY` env var (sidecar default
  `hi_res`; the frontend launches it with `fast`).
- `WorkDir` must be a directory shared by IRIS and the sidecar (same host).
- Run it manually with:
  ```
  python -m uvicorn sidecar.extract_service:app --host 127.0.0.1 --port 8800
  ```
  or let `frontend/app.py` auto-start it (set `AUTOSTART_SIDECAR=0` to disable).

## Notes

- `Embedding.Clinical` schema + HNSW index are created on first load by
  `LoadOperation`. On re-load of an existing slug it deletes the slug's rows before
  re-inserting; because deleting then re-inserting against a **live HNSW index** can
  raise during the INSERT, re-ingest of an already-loaded slug is blocked up front by
  the duplicate guard rather than going through Load.
- Secrets are stored in IRIS credentials (`OpenAIKey`/`TavilyKey`), not `.env`.
- Tunables are production SETTINGS: `MaxIterations`, `DefaultTopK` (Agent Process),
  `Model` (LLM Operation), `SidecarURL`/`WorkDir`/`RequestTimeout` (Prepare Operation;
  `RequestTimeout` defaults to 3600s for slow extractions).
