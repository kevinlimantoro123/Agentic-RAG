"""FastAPI front door for the LangGraph agent — replaces the IRIS query path
(RAG2026.BS.QueryService + RAG2026.REST.Dispatch.Query).

  GET  /health            -> {"status":"ok"}
  POST /query  {"question","thread_id","pdf","patient","visit_date","resource","top_k"}
               -> {"answer","tool_log":[{tool,args,result}]}

`thread_id` keys the conversation: reuse it for follow-ups, send a new one to
start a fresh chat. If omitted, each call is a one-shot (a random id is used).

Run with:
  uvicorn agent.server:app --host 127.0.0.1 --port 8001
"""

from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from .graph import run_agent

app = FastAPI(title="Agentic Clinical RAG (LangGraph)")


class QueryRequest(BaseModel):
    question: str
    thread_id: str | None = None  # conversation key; omit for a one-shot turn
    pdf: str = ""
    patient: str = ""
    visit_date: str = ""
    resource: str = ""
    top_k: int | None = None
    max_iterations: int | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest):
    return run_agent(
        question=req.question,
        thread_id=req.thread_id or str(uuid4()),
        pdf=req.pdf,
        patient=req.patient,
        visit_date=req.visit_date,
        resource=req.resource,
        top_k=req.top_k,
        max_iterations=req.max_iterations,
    )
