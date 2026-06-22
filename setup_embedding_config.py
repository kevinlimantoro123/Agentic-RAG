"""One-off: register the embedding config used by Embedding.Clinical.

Uses OpenAI's text-embedding-3-small via IRIS %Embedding.OpenAI so the model
runs as an HTTPS API call (no local torch loaded into the IRIS process).

The config is registered as 'openai-embedding-config' in loader.py and test_rag.py.

Run once with the project venv:
    venv/Scripts/python.exe setup_embedding_config.py
"""
import json
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY not set in .env")

engine = create_engine(os.getenv("IRIS_CONN_STR"))

config = {
    "apiKey": OPENAI_API_KEY,
    "sslConfig": "llm_ssl",
    "modelName": "text-embedding-3-small",
}

with engine.begin() as conn:
    conn.execute(text("DELETE FROM %Embedding.Config WHERE Name = 'openai-embedding-config'"))
    conn.execute(
        text(
            "INSERT INTO %Embedding.Config "
            "(Name, Configuration, EmbeddingClass, VectorLength, Description) "
            "VALUES ('openai-embedding-config', :cfg, '%Embedding.OpenAI', 1536, "
            "'OpenAI text-embedding-3-small')"
        ),
        {"cfg": json.dumps(config)},
    )

with engine.connect() as conn:
    rows = conn.execute(
        text("SELECT Name, EmbeddingClass, VectorLength FROM %Embedding.Config")
    ).fetchall()

print("Registered embedding configs:")
for r in rows:
    print("  ", r[0], "|", r[1], "| dim", r[2])
