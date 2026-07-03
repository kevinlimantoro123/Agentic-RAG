"""Environment configuration for the LangGraph agent.

All secrets come from the process environment / .env (NOT IRIS credentials):
  OPENAI_API_KEY   used by ChatOpenAI (was the IRIS `OpenAIKey` credential)
  TAVILY_API_KEY   used by langchain_tavily (was the IRIS `TavilyKey` credential)

Retrieval still runs inside IRIS, reached over HTTP:
  IRIS_REST_URL    base URL of the IRIS web app, e.g. http://localhost:52773/csp/rag2026
  IRIS_USER        HTTP Basic user ("" disables auth, for Unauthenticated web apps)
  IRIS_PASSWORD    HTTP Basic password
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ── LLM (replaces RAG2026.BO.LLMOperation) ───────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # matches the production default

# ── Guideline search (replaces RAG2026.BO.GuidelineOperation) ────────────────
# langchain_tavily reads TAVILY_API_KEY from the environment; load_dotenv puts it there.
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# ── Retrieval: the one tool that stays in IRIS (RAG2026.BO.RetrieveOperation) ─
IRIS_REST_URL = os.getenv("IRIS_REST_URL", "http://localhost:52773/csp/rag2026").rstrip("/")
IRIS_USER = os.getenv("IRIS_USER", "SuperUser")
IRIS_PASSWORD = os.getenv("IRIS_PASSWORD", "SYS")
# Only send Basic auth when a user is configured (mirrors frontend/app.py).
IRIS_AUTH = (IRIS_USER, IRIS_PASSWORD) if IRIS_USER else None

# ── Agent tunables (mirror the Agent Process SETTINGS) ───────────────────────
MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
DEFAULT_TOP_K = int(os.getenv("AGENT_DEFAULT_TOP_K", "5"))
RETRIEVE_TIMEOUT = int(os.getenv("AGENT_RETRIEVE_TIMEOUT", "60"))
