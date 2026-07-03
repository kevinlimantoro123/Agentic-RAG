"""The LangGraph agent — replaces RAG2026.BP.AgentProcess.

`create_react_agent` runs the whole call-model -> dispatch-tools -> feed-results
-> loop cycle that AgentProcess.OnRequest did by hand. The system prompt and the
per-request context note are copied verbatim from AgentProcess so behaviour matches.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from . import config
from .llm import build_llm
from .tools import make_tools

# Verbatim from RAG2026.BP.AgentProcess.SystemPrompt().
SYSTEM_PROMPT = (
    "You are a careful clinical AI assistant helping clinicians answer medical questions.\n\n"
    "You have access to two tools:\n"
    "- retrieve_patient_records: searches the clinical notes database using HNSW vector search\n"
    "- guideline_search: fetches evidence-based guidelines from ACE, NICE, NDF, HSA, FDA, NIH, or CDC\n\n"
    "For each question:\n"
    "1. Call retrieve_patient_records to fetch relevant patient notes from the database.\n"
    "2. Call guideline_search on the most appropriate authoritative source for evidence-based context.\n"
    "3. You may call tools multiple times with refined queries if the initial results are insufficient.\n"
    "4. When you have enough information, synthesise a clear, well-cited answer.\n\n"
    "Cite patient records as [P1], [P2], ... and guideline snippets as [G1], [G2], ...\n"
    "If the combined data is still insufficient, say so explicitly."
)


def _context_note(ctx: dict) -> str:
    """Per-request context note, mirroring AgentProcess.ContextNote()."""
    note = "Active document: " + (ctx.get("pdf") or "none")
    if ctx.get("patient"):
        note += " | Patient filter: " + ctx["patient"]
    if ctx.get("visit_date"):
        note += " | Date filter: " + ctx["visit_date"]
    if ctx.get("resource"):
        note += (
            " | Preferred guideline source: " + ctx["resource"]
            + " (prefer this source for guideline_search unless another is clearly more appropriate)"
        )
    return note


# The chat model is stateless, so build it once and reuse across requests.
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


def run_agent(
    question: str,
    pdf: str = "",
    patient: str = "",
    visit_date: str = "",
    resource: str = "",
    top_k: int | None = None,
    max_iterations: int | None = None,
) -> dict:
    """Run the agentic loop for one question. Returns {answer, tool_log} in the
    same shape the Streamlit frontend already expects from the IRIS /query."""
    ctx = {
        "pdf": pdf or "",
        "patient": patient or "",
        "visit_date": visit_date or "",
        "resource": resource or "",
        "top_k": top_k if (top_k and top_k > 0) else config.DEFAULT_TOP_K,
    }

    # Tools are bound to this request's context (arg-merging like AgentProcess.Dispatch).
    agent = create_react_agent(_get_llm(), make_tools(ctx), prompt=SYSTEM_PROMPT)

    max_iter = max_iterations if (max_iterations and max_iterations > 0) else config.MAX_ITERATIONS
    # A ReAct turn is two graph steps (agent node + tool node), plus a final agent node.
    recursion_limit = max_iter * 2 + 1

    result = agent.invoke(
        {"messages": [SystemMessage(content=_context_note(ctx)), HumanMessage(content=question)]},
        config={"recursion_limit": recursion_limit},
    )

    messages = result["messages"]
    return {
        "answer": _final_answer(messages),
        "tool_log": _build_tool_log(messages),
    }


def _final_answer(messages) -> str:
    """The last assistant turn with no tool calls is the final answer."""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            return m.content or ""
    return "Maximum reasoning steps reached without a conclusive answer."


def _build_tool_log(messages) -> list:
    """Reconstruct the [{tool, args, result}] log the frontend renders, pairing
    each tool call with its result message in execution order."""
    calls: dict = {}  # tool_call_id -> {tool, args}
    log = []
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                calls[tc["id"]] = {"tool": tc["name"], "args": tc.get("args", {})}
        elif isinstance(m, ToolMessage):
            meta = calls.get(m.tool_call_id, {"tool": m.name, "args": {}})
            try:
                parsed = json.loads(m.content)
            except (json.JSONDecodeError, TypeError):
                parsed = m.content
            log.append({"tool": meta["tool"], "args": meta["args"], "result": parsed})
    return log
