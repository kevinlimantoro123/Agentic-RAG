"""
True agentic RAG loop using OpenAI function calling.

GPT-4o decides which tools to call and when, iterating until it has
enough context to answer. Tools available:
  - retrieve_patient_records: semantic search over IRIS clinical DB
  - guideline_search: authoritative web sources (NICE, FDA, CDC, etc.)
"""

from __future__ import annotations

import json
import os
from typing import Generator

import openai
from dotenv import load_dotenv

from rag_tool.test_rag import RESOURCE_DOMAINS, guideline_search, retrieve_text_chunks

load_dotenv()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """\
You are a careful clinical AI assistant helping clinicians answer medical questions.

You have access to two tools:
- retrieve_patient_records: searches the clinical notes database using HNSW vector search
- guideline_search: fetches evidence-based guidelines from ACE, NICE, NDF, HSA, FDA, NIH, or CDC

For each question:
1. Call retrieve_patient_records to fetch relevant patient notes from the database.
2. Call guideline_search on the most appropriate authoritative source for evidence-based context.
3. You may call tools multiple times with refined queries if the initial results are insufficient.
4. When you have enough information, synthesise a clear, well-cited answer.

Cite patient records as [P1], [P2], … and guideline snippets as [G1], [G2], …
If the combined data is still insufficient, say so explicitly.
"""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_patient_records",
            "description": (
                "Semantic search over the clinical notes database using HNSW vector similarity. "
                "Returns matching records with visit date and clinical text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "pdf": {
                        "type": "string",
                        "description": "Document/PDF slug to search within",
                    },
                    "patient": {
                        "type": "string",
                        "description": "Patient name substring filter (optional)",
                    },
                    "visit_date": {
                        "type": "string",
                        "description": "Date filter: YYYY, YYYY-MM, or YYYY-MM-DD (optional)",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum records to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query", "pdf"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guideline_search",
            "description": (
                "Fetch medication guidelines, dosing, or safety information from an authoritative "
                "clinical resource. Choose the most relevant source for the question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "resource": {
                        "type": "string",
                        "enum": list(RESOURCE_DOMAINS.keys()),
                        "description": "Authoritative source to query",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 3,
                    },
                },
                "required": ["query", "resource"],
            },
        },
    },
]


def _dispatch(fn_name: str, fn_args: dict, default_pdf: str, default_patient: str | None,
              default_visit_date: str | None, default_top_k: int) -> list[dict]:
    if fn_name == "retrieve_patient_records":
        return retrieve_text_chunks(
            query=fn_args["query"],
            slug=fn_args.get("pdf") or default_pdf,
            top_k=fn_args.get("top_k") or default_top_k,
            patient=fn_args.get("patient") or default_patient,
            visit_date=fn_args.get("visit_date") or default_visit_date,
        )
    if fn_name == "guideline_search":
        return guideline_search(
            query=fn_args["query"],
            resource=fn_args["resource"],
            max_results=fn_args.get("max_results", 3),
        )
    return [{"error": f"Unknown tool: {fn_name}"}]


def run_agent(
    question: str,
    pdf: str,
    patient: str | None = None,
    visit_date: str | None = None,
    top_k: int = 5,
    max_iterations: int = 10,
) -> tuple[str, list[dict]]:
    """
    Run the agentic RAG loop.

    Returns:
        (answer, tool_call_log)
        tool_call_log: list of {"tool", "args", "result"} for UI display.
    """
    context_note = f"Active document: {pdf or 'none'}"
    if patient:
        context_note += f" | Patient filter: {patient}"
    if visit_date:
        context_note += f" | Date filter: {visit_date}"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_note},
        {"role": "user", "content": question},
    ]

    tool_call_log: list[dict] = []

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # Append assistant turn (convert to dict so it serialises cleanly)
        assistant_turn: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if not msg.tool_calls:
            return (msg.content or "").strip(), tool_call_log

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            result = _dispatch(fn_name, fn_args, pdf, patient, visit_date, top_k)

            tool_call_log.append({"tool": fn_name, "args": fn_args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    return "Maximum reasoning steps reached without a conclusive answer.", tool_call_log


def run_agent_streaming(
    question: str,
    pdf: str,
    patient: str | None = None,
    visit_date: str | None = None,
    top_k: int = 5,
    max_iterations: int = 10,
) -> Generator[dict, None, None]:
    """
    Streaming variant: yields status events for real-time UI updates.

    Event types:
      {"type": "tool_start",  "tool": name, "args": {...}}
      {"type": "tool_result", "tool": name, "result": [...]}
      {"type": "answer",      "text": "..."}
      {"type": "error",       "text": "..."}
    """
    context_note = f"Active document: {pdf or 'none'}"
    if patient:
        context_note += f" | Patient filter: {patient}"
    if visit_date:
        context_note += f" | Date filter: {visit_date}"

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_note},
        {"role": "user", "content": question},
    ]

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        assistant_turn: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if not msg.tool_calls:
            yield {"type": "answer", "text": (msg.content or "").strip()}
            return

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            yield {"type": "tool_start", "tool": fn_name, "args": fn_args}
            result = _dispatch(fn_name, fn_args, pdf, patient, visit_date, top_k)
            yield {"type": "tool_result", "tool": fn_name, "result": result}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })

    yield {"type": "error", "text": "Maximum reasoning steps reached without a conclusive answer."}
