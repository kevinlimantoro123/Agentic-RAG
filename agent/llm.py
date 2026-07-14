"""The chat model — the LangChain equivalent of RAG2026.BO.LLMOperation.

In the IRIS design, LLMOperation was a single stateless OpenAI chat call and the
loop lived in AgentProcess. Here the loop lives in LangGraph, and this is just the
model it drives; LangGraph handles the call / tool_calls / feed-back cycle.
"""

from langchain_openai import ChatOpenAI

from . import config


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=0,
        api_key=config.OPENAI_API_KEY,
    )
