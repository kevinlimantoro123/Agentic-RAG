"""The LangGraph agent — replaces RAG2026.BP.AgentProcess.

`create_react_agent` runs the whole call-model -> dispatch-tools -> feed-results
-> loop cycle that AgentProcess.OnRequest did by hand. The system prompt and the
per-request context note are copied verbatim from AgentProcess so behaviour matches.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
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

# In-memory conversation store, keyed by thread_id. Not durable: history is lost
# when this process restarts, and it is NOT shared across multiple uvicorn workers
# (run a single worker, or swap in SqliteSaver/Postgres for either of those).
_checkpointer = MemorySaver()


def _get_llm():
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


def run_agent(
    question: str,
    thread_id: str,
    pdf: str = "",
    patient: str = "",
    visit_date: str = "",
    resource: str = "",
    top_k: int | None = None,
    max_iterations: int | None = None,
) -> dict:
    """Run one turn of the agentic loop. Conversation history for `thread_id` is
    loaded and saved automatically by the checkpointer, so only the new question
    is sent. Returns {answer, tool_log} in the shape the frontend expects."""
    ctx = {
        "pdf": pdf or "",
        "patient": patient or "",
        "visit_date": visit_date or "",
        "resource": resource or "",
        "top_k": top_k if (top_k and top_k > 0) else config.DEFAULT_TOP_K,
    }

    # The context note goes into the prompt (applied fresh each turn, not stored)
    # rather than into the messages, so per-turn filters stay current and don't
    # accumulate a stale system message on every turn.
    prompt = SYSTEM_PROMPT + "\n\n" + _context_note(ctx)

    # Tools are bound to this request's context (arg-merging like AgentProcess.Dispatch).
    agent = create_react_agent(
        _get_llm(), make_tools(ctx), prompt=prompt, checkpointer=_checkpointer
    )

    max_iter = max_iterations if (max_iterations and max_iterations > 0) else config.MAX_ITERATIONS
    # A ReAct turn is two graph steps (agent node + tool node), plus a final agent node.
    recursion_limit = max_iter * 2 + 1

    # Send only the new turn; the checkpointer supplies the prior history.
    result = agent.invoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit},
    )

    messages = result["messages"]  # full accumulated history for this thread
    return {
        "answer": _final_answer(messages),
        # Only this turn's tool calls, not every past turn's.
        "tool_log": _build_tool_log(_current_turn(messages)),
    }


def _current_turn(messages) -> list:
    """The messages produced by the latest turn: everything from the last user
    message onward (the checkpointer returns the entire conversation)."""
    human_idxs = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if not human_idxs:
        return messages
    return messages[human_idxs[-1]:]


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
