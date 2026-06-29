import json, os, sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
from dotenv import load_dotenv
try:
    from pipeline.embedder import embed_chunks   # run as a module from repo root
except ImportError:
    from embedder import embed_chunks             # run directly from pipeline/

# ─── config ───────────────────────────────────────────────────────────────
load_dotenv()                              
IRIS_CONN_STR = os.getenv("IRIS_CONN_STR")
if not IRIS_CONN_STR:
    print("❌ IRIS_CONN_STR is not set in your .env", file=sys.stderr)
    sys.exit(1)

engine = create_engine(IRIS_CONN_STR)        

# ─── loader function ──────────────────────────────────────────────────────
def load_chunks_to_iris(pdf_slug: str, chunks_json_path: str) -> None:
    tbl = f"Embedding.Clinical"
    # begin a transaction
    with engine.begin() as conn:
      # 1) Create table if missing
      conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {tbl} (
          Name VARCHAR(200),
          Length INT,
          Description LONGVARCHAR,
          DescriptionEmbedding VECTOR(DOUBLE, 1536),
          Patient VARCHAR(50),
          VisitDate VARCHAR(50),
          PDF VARCHAR(50)
        )
      """))

      # 1. check if the index is already there
      exists = conn.execute(text(f"""
        SELECT COUNT(*) AS cnt
          FROM INFORMATION_SCHEMA.INDEXES
        WHERE TABLE_SCHEMA  = 'Embedding'
          AND TABLE_NAME    = 'Clinical'
          AND INDEX_NAME    = 'HNSWIndex'
      """), { "tbl": pdf_slug }).scalar()

      # 2. only create it if it’s missing
      if exists == 0:
          conn.execute(text(f"""
            CREATE INDEX HNSWIndex 
            ON TABLE {tbl} (DescriptionEmbedding)
            AS HNSW(M=32, efConstruction=100, Distance='DotProduct')
          """))

      # 3) Load the JSON file
      path = Path(chunks_json_path)
      if not path.exists():
          raise FileNotFoundError(f"chunks.json not found at: {path}")
      with open(path, "r", encoding="utf-8") as f:
          chunks = json.load(f)

      # Batch-embed any chunks that don't already carry a vector (no-op if the
      # sidecar already embedded them), so the INSERTs below stay pure SQL.
      embed_chunks(chunks)

      insert_sql = text(f"""
        INSERT INTO {tbl}
          (Description, Length, Name, Patient, VisitDate, PDF, DescriptionEmbedding)
        VALUES (:text, :tokens, :heading, :patient, :visitdate, :pdf,
                TO_VECTOR(:emb, DOUBLE, 1536))
      """)

      # 5) Iterate & insert
      inserted = 0
      for idx, chunk in enumerate(chunks, start=1):
          text_val   = chunk.get("text", "")
          heading    = chunk.get("heading", "")
          tokens     = chunk.get("tokens", 0)
          patient    = chunk.get("patient", "")
          visitdate  = chunk.get("visitdate", "")
          pdf = chunk.get("pdf", "")

          if not text_val:
              print(f"⚠ Skipping empty chunk #{idx}")
              continue

          emb = chunk.get("embedding")
          emb_str = ",".join(repr(float(x)) for x in emb) if emb else None

          try:
              conn.execute(insert_sql, {
                  "text":      text_val,
                  "tokens":    tokens,
                  "heading":   heading,
                  "patient":   patient,
                  "visitdate": visitdate,
                  "pdf": pdf,
                  "emb": emb_str
              })
              inserted += 1
          except SQLAlchemyError as e:
              print(f"❌ Insert failed at chunk #{idx}: {e}")

    print(f"✅ Done. Inserted {inserted} rows into {tbl}")
    return inserted

# ─── CLI entrypoint ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Load chunks.json into IRIS")
    p.add_argument("slug", help="PDF slug (matches your directory name & table suffix)")
    p.add_argument("json_path", help="Path to chunks.json")
    args = p.parse_args()
    load_chunks_to_iris(args.slug, args.json_path)
