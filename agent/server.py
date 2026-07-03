"""FastAPI front door for the LangGraph agent — replaces the IRIS query path
(RAG2026.BS.QueryService + RAG2026.REST.Dispatch.Query).

  GET  /health            -> {"status":"ok"}
  POST /query  {"question","pdf","patient","visit_date","resource","top_k"}
               -> {"answer","tool_log":[{tool,args,result}]}

Run with:
  uvicorn agent.server:app --host 127.0.0.1 --port 8001
"""

from fastapi import FastAPI
from pydantic import BaseModel

from .graph import run_agent

app = FastAPI(title="Agentic Clinical RAG (LangGraph)")


class QueryRequest(BaseModel):
    question: str
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
        pdf=req.pdf,
        patient=req.patient,
        visit_date=req.visit_date,
        resource=req.resource,
        top_k=req.top_k,
        max_iterations=req.max_iterations,
    )
