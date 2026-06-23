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
7. **Start the production**: Interoperability → Configure → Production →
   `RAG2026.Production` → Start. (Set Auto-Start for the VM.)

## REST API

```
GET  /csp/rag2026/health
POST /csp/rag2026/query    {"question","pdf","patient","visit_date","resource","top_k"}
POST /csp/rag2026/ingest   {"slug","pdf_base64"}
```

## Extractor sidecar contract (the only non-IRIS piece — not yet written)

A small FastAPI app in your existing Python venv, wrapping `pipeline/`:

```
POST {SidecarURL}      e.g. http://127.0.0.1:8800/prepare
  body    {"slug": "...", "pdf_path": "<WorkDir>/<slug>/<slug>.pdf", "work_dir": "..."}
  action  run extractor.py -> cleaner.py -> chunker.py, writing chunks.json
  return  {"chunks_path": "<WorkDir>/<slug>/chunks.json", "stats": {...}}
```

`WorkDir` must be a directory shared by IRIS and the sidecar (same host). Run the
sidecar as a systemd service. Ask Claude to generate this file next.

## Notes

- `Embedding.Clinical` schema + HNSW index are created on first load by
  `LoadOperation` — identical to the old `pipeline/loader.py`, so existing data is
  compatible.
- Secrets are stored in IRIS credentials (`OpenAIKey`/`TavilyKey`), not `.env`.
- Tunables are production SETTINGS: `MaxIterations`, `DefaultTopK` (Agent Process),
  `Model` (LLM Operation), `SidecarURL`/`WorkDir`/`RequestTimeout` (Prepare Operation).
