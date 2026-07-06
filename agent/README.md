# `agent/` — LangGraph agentic loop (out of IRIS)

This package moves the **agentic query loop** out of IRIS Interoperability into a
LangGraph ReAct agent, while **keeping retrieval in IRIS** and leaving the entire
ingest path untouched.

## What moved, what stayed

| Old (IRIS) | New |
|---|---|
| `RAG2026.BP.AgentProcess` (the loop) | `agent/graph.py` — `create_react_agent` |
| `RAG2026.BO.LLMOperation` | `agent/llm.py` — `ChatOpenAI` (LangGraph runs the loop) |
| `RAG2026.BO.GuidelineOperation` | `agent/tools.py` — `guideline_search` (Tavily) |
| `RAG2026.BO.RetrieveOperation` | **unchanged, still in IRIS** — reached via `POST /retrieve` |
| `RAG2026.BS.QueryService` + REST `/query` | `agent/server.py` — FastAPI `/query` |

The old IRIS classes are **left on disk** (nothing deleted); the query path just no
longer exercises `AgentProcess` / `LLMOperation` / `GuidelineOperation`.

## Data flow

```
Streamlit ──POST /query──► agent/server.py (FastAPI)
                              └─ graph.run_agent  (LangGraph ReAct loop)
                                   ├─ ChatOpenAI ─────────────────► OpenAI
                                   ├─ guideline_search ── Tavily ─► *.gov / NICE / ...
                                   └─ retrieve_patient_records
                                        └─POST /retrieve─► IRIS: Retrieve Service
                                                            → Retrieve Operation
                                                            → Embedding.Clinical (HNSW)
```

Ingest (`/ingest`, pdfs, patients, dedup, health) still goes straight to IRIS.

## IRIS-side additions (must be loaded into IRIS)

Load the updated classes into the `RAG2026` namespace and **restart the production**
(a new business service was added):

- `src/RAG2026/BS/RetrieveService.cls` — new pass-through BS → Retrieve Operation.
- `src/RAG2026/Production.cls` — registers **Retrieve Service** (Query category).
- `src/RAG2026/REST/Dispatch.cls` — new route `POST /retrieve`.

```objectscript
zn "RAG2026"  do $SYSTEM.OBJ.LoadDir("/path/to/repo/src/RAG2026","ck",,1)
```
Then Interoperability → restart `RAG2026.Production`.

Smoke-test the new endpoint directly:
```bash
curl -u SuperUser:SYS -X POST http://localhost:52773/csp/rag2026/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"metformin dose","pdf":"<a-loaded-slug>","top_k":3}'
# -> [{"label":"P1","date":"...","text":"..."}]
```

## Configuration (env / `.env`)

| Var | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | ChatOpenAI (was IRIS `OpenAIKey` credential) |
| `OPENAI_MODEL` | `gpt-4o` | chat model |
| `TAVILY_API_KEY` | — | guideline search (was IRIS `TavilyKey` credential) |
| `IRIS_REST_URL` | `http://localhost:52773/csp/rag2026` | base URL for `/retrieve` |
| `IRIS_USER` / `IRIS_PASSWORD` | `SuperUser` / `SYS` | Basic auth (`IRIS_USER=""` disables) |
| `AGENT_MAX_ITERATIONS` | `10` | LLM↔tool iterations (was `MaxIterations`) |
| `AGENT_DEFAULT_TOP_K` | `5` | default retrieval top-k (was `DefaultTopK`) |
| `AGENT_URL` (frontend) | `http://localhost:8001` | where the frontend sends `/query` |

## Run

```bash
pip install -r requirements.txt          # adds langgraph + langchain-openai

# 1) the agent service
uvicorn agent.server:app --host 127.0.0.1 --port 8001

# 2) the frontend (points /query at AGENT_URL, everything else at IRIS)
streamlit run frontend/app.py
```

Quick check without the UI:
$body = @{
  question = "What is the patient history?"
  pdf      = "rag dummy pdf"
  resource = "NICE"
  top_k    = 5
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8001/query" -ContentType "application/json" -Body $body


## Multi-turn memory

The agent remembers earlier turns within a conversation, keyed by a **`thread_id`**
sent with each `/query`:

- Reuse the same `thread_id` for follow-ups ("and her kidney function?"); send a
  new one to start fresh. If `thread_id` is omitted, the turn is a one-shot.
- The Streamlit UI holds a `thread_id` in session state and exposes a **New
  conversation** button that rotates it.
- Storage is `MemorySaver` (in-process): history is **lost on restart** and is **not
  shared across uvicorn workers** — run a single worker. For durability swap in
  `SqliteSaver` (`langgraph-checkpoint-sqlite`) or Postgres in `agent/graph.py`.

## Notes

- `create_react_agent` is imported from **`langgraph.prebuilt`** (native tool-calling),
  not `langchain.agents` (the older string-parsing ReAct). On LangChain 1.0 the
  equivalent is `langchain.agents.create_agent`; if you upgrade, swap the import in
  `agent/graph.py`.
- Tools are rebuilt per request (`make_tools(ctx)`) so the sidebar filters (pdf /
  patient / visit_date) act as fallbacks when the LLM omits them — reproducing
  `AgentProcess.Dispatch`'s arg-merging.
- API keys for the LLM and guideline search now live in the agent process's env,
  **not** IRIS credentials. Retrieval still uses the IRIS-stored key server-side.
