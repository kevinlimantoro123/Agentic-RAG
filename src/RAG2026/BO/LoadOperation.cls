Include Ensemble

/// Load business operation: bulk-loads a chunks.json into Embedding.Clinical.
/// Embeddings are precomputed in batches by the sidecar (pipeline/embedder.py) and
/// carried in chunks.json, so this operation only does fast INSERTs of text +
/// vector (TO_VECTOR) and never makes a per-row embedding call. IRIS maintains the
/// HNSW index on the manually-populated DescriptionEmbedding VECTOR column.
Class RAG2026.BO.LoadOperation Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Parameter SETTINGS = "EmbeddingConfig:Basic";

/// Name of the registered %Embedding.Config used by Embedding.Clinical.
Property EmbeddingConfig As %String [ InitialExpression = "openai-embedding-config" ];

XData MessageMap
{
<MapItems>
  <MapItem MessageType="RAG2026.Msg.LoadRequest">
    <Method>OnLoad</Method>
  </MapItem>
</MapItems>
}

Method OnLoad(pRequest As RAG2026.Msg.LoadRequest, Output pResponse As RAG2026.Msg.LoadResponse) As %Status
{
    set tSC = $$$OK
    set pResponse = ##class(RAG2026.Msg.LoadResponse).%New()
    try {
        set pResponse.RowsInserted = ..LoadChunks(pRequest.Slug, pRequest.ChunksPath, ..EmbeddingConfig)
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method LoadChunks(pSlug As %String, pChunksPath As %String, pConfig As %String) As %Integer [ Language = python ]
{
    import iris, json, os

    if not pChunksPath or not os.path.exists(pChunksPath):
        raise FileNotFoundError("chunks.json not found at: " + str(pChunksPath))

    # 1) Create the table if missing. DescriptionEmbedding is a plain VECTOR we
    #    populate ourselves from precomputed vectors (NOT an EMBEDDING() computed
    #    column), so inserts never trigger a server-side OpenAI call.
    create_sql = (
        "CREATE TABLE IF NOT EXISTS Embedding.Clinical ("
        "Name VARCHAR(200), "
        "Length INT, "
        "Description LONGVARCHAR, "
        "DescriptionEmbedding VECTOR(DOUBLE, 1536), "
        "Patient VARCHAR(50), "
        "VisitDate VARCHAR(50), "
        "PDF VARCHAR(50))"
    )
    iris.sql.exec(create_sql)

    # 2) Ensure the HNSW index exists, idempotently. iris.sql.exec raises if it
    #    already exists, and the INFORMATION_SCHEMA existence check was unreliable
    #    inside the production job (returned 0 even when present), so just attempt
    #    the create and tolerate an already-existing index.
    try:
        iris.sql.exec(
            "CREATE INDEX HNSWIndex ON TABLE Embedding.Clinical (DescriptionEmbedding) "
            "AS HNSW(M=32, efConstruction=100, Distance='DotProduct')"
        )
    except Exception:
        pass  # index already exists -> nothing to do

    # 3) Make the load idempotent: drop any existing rows for this slug. A DELETE
    #    that matches no rows returns SQLCODE 100, which iris.sql.exec surfaces as
    #    an (empty-message) SQLError -- "nothing to delete" is not an error.
    try:
        iris.sql.exec("DELETE FROM Embedding.Clinical WHERE PDF = ?", pSlug)
    except Exception as ex:
        if getattr(ex, "sqlcode", None) != 100:
            raise

    # 4) Load chunks.
    with open(pChunksPath, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    insert_sql = (
        "INSERT INTO Embedding.Clinical "
        "(Description, Length, Name, Patient, VisitDate, PDF, DescriptionEmbedding) "
        "VALUES (?, ?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE, 1536))"
    )

    inserted = 0
    for chunk in chunks:
        text_val = chunk.get("text", "")
        if not text_val:
            continue
        emb = chunk.get("embedding")
        # Fail loudly rather than store a useless zero vector: TO_VECTOR(NULL)
        # materializes as all-zeros in IRIS, which silently breaks search. A
        # missing embedding means the sidecar embed step didn't run (stale process
        # or pre-change chunks.json) -- restart the sidecar and re-prepare.
        if not emb:
            raise ValueError(
                "chunks.json chunk has no precomputed 'embedding'; "
                "restart the sidecar so /prepare embeds chunks before Load."
            )
        emb_str = ",".join(repr(float(x)) for x in emb)
        iris.sql.exec(
            insert_sql,
            text_val,
            chunk.get("tokens", 0),
            chunk.get("heading", ""),
            chunk.get("patient", ""),
            chunk.get("visitdate", ""),
            chunk.get("pdf", "") or pSlug,
            emb_str,
        )
        inserted += 1

    return inserted
}

}
