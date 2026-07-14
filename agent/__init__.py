"""LangGraph agentic RAG — the out-of-IRIS agent loop.

This package replaces the in-IRIS query path (RAG2026.BP.AgentProcess +
RAG2026.BO.LLMOperation + RAG2026.BO.GuidelineOperation) with a LangGraph
ReAct agent. Retrieval stays in IRIS: the `retrieve_patient_records` tool calls
the IRIS REST endpoint POST /retrieve, which runs RAG2026.BO.RetrieveOperation
(HNSW over Embedding.Clinical). The ingest path is untouched.
"""

from .graph import run_agent

__all__ = ["run_agent"]
