"""
Batch embedder for chunk texts.

Calls OpenAI's text-embedding-3-small with ARRAYS of inputs (up to a token/item
budget per request) instead of one input per call. This turns N single-input
HTTP round-trips into N/MAX_ITEMS calls -- the dominant speedup for loading big
PDFs. Vectors are written into each chunk dict so the IRIS Load operation only
does fast bulk inserts (TO_VECTOR) with no embedding work of its own.

Runs in the project .venv (openai + tiktoken are in requirements.txt), i.e. in
the sidecar process or the loader.py CLI -- NOT inside IRIS embedded Python.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

MODEL = "text-embedding-3-small"
DIM = 1536
# text-embedding-3-* allows up to 2048 inputs and ~300k tokens per request.
# Stay well under both: clinical chunks are small, so a 128-item / 250k-token
# budget keeps each request comfortably valid.
MAX_ITEMS_PER_REQUEST = 128
MAX_TOKENS_PER_REQUEST = 250_000


def _client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set; cannot embed chunks")
    from openai import OpenAI
    return OpenAI(api_key=key)


def _encoder():
    import tiktoken
    try:
        return tiktoken.encoding_for_model(MODEL)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _token_len(text: str, enc) -> int:
    try:
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts, preserving input order. Empty strings are sent as a single
    space (the API rejects empty input). Returns one DIM-length vector per text."""
    if not texts:
        return []

    enc = _encoder()
    client = _client()
    vectors: list[list[float] | None] = [None] * len(texts)

    batch_idx: list[int] = []
    batch_tokens = 0

    def flush():
        nonlocal batch_idx, batch_tokens
        if not batch_idx:
            return
        inputs = [texts[i] or " " for i in batch_idx]
        resp = client.embeddings.create(model=MODEL, input=inputs, dimensions=DIM)
        # resp.data[*].index is the position within THIS request's input list.
        for item in resp.data:
            vectors[batch_idx[item.index]] = item.embedding
        batch_idx, batch_tokens = [], 0

    for i, t in enumerate(texts):
        tl = _token_len(t or " ", enc)
        if batch_idx and (
            len(batch_idx) >= MAX_ITEMS_PER_REQUEST
            or batch_tokens + tl > MAX_TOKENS_PER_REQUEST
        ):
            flush()
        batch_idx.append(i)
        batch_tokens += tl
    flush()

    return [v if v is not None else [] for v in vectors]


def embed_chunks(chunks: list[dict], skip_existing: bool = True) -> list[dict]:
    """Add 'embedding' (list[float]) to each chunk in-place, derived from its
    'text'. Chunks with empty text get embedding=None. With skip_existing, chunks
    that already carry a list 'embedding' are left untouched (so re-running on an
    already-embedded chunks.json costs nothing)."""
    todo = [
        i
        for i, c in enumerate(chunks)
        if c.get("text")
        and not (skip_existing and isinstance(c.get("embedding"), list) and c["embedding"])
    ]
    vecs = embed_texts([chunks[i]["text"] for i in todo])
    for i, v in zip(todo, vecs):
        chunks[i]["embedding"] = v
    for c in chunks:
        c.setdefault("embedding", None)
    return chunks
