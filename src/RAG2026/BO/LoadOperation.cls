Include Ensemble

/// Load business operation: bulk-loads a chunks.json into Embedding.Clinical.
/// IRIS generates the OpenAI embeddings server-side (the EMBEDDING(...) columns)
/// and maintains the HNSW index. Native port of pipeline/loader.py via iris.sql.
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
        set pResponse.RowsInserted = ..LoadChunks(pRequest.Slug, pRequest.ChunksPath, ..EmbeddingConfig, pRequest.Hash)
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method LoadChunks(pSlug As %String, pChunksPath As %String, pConfig As %String, pHash As %String = "") As %Integer [ Language = python ]
{
    import iris, json, os

    if not pChunksPath or not os.path.exists(pChunksPath):
        raise FileNotFoundError("chunks.json not found at: " + str(pChunksPath))

    def create_hnsw():
        # iris.sql.exec raises if the index already exists, and the
        # INFORMATION_SCHEMA existence check was unreliable inside the
        # production job (returned 0 even when present), so just attempt the
        # create and tolerate an already-existing index.
        try:
            iris.sql.exec(
                "CREATE INDEX HNSWIndex ON TABLE Embedding.Clinical (DescriptionEmbedding) "
                "AS HNSW(M=32, efConstruction=100, Distance='DotProduct')"
            )
        except Exception:
            pass  # index already exists -> nothing to do

    # 1) Create the table if missing (server-side OpenAI embedding columns).
    create_sql = (
        "CREATE TABLE IF NOT EXISTS Embedding.Clinical ("
        "Name VARCHAR(200), "
        "Length INT, "
        "Description LONGVARCHAR, "
        "DescriptionEmbedding EMBEDDING('" + pConfig + "','Description'), "
        "Patient VARCHAR(50), "
        "VisitDate VARCHAR(50), "
        "PDF VARCHAR(50), "
        "Hash VARCHAR(64))"
    )
    iris.sql.exec(create_sql)

    # 1b) Migration-safe: add the Hash column if this is a pre-existing table
    #     created before content-hash dedup. Tolerate "already exists".
    try:
        iris.sql.exec("ALTER TABLE Embedding.Clinical ADD COLUMN Hash VARCHAR(64)")
    except Exception:
        pass

    # 2) Is this a re-load of an already-present slug? (Content mode lets a
    #    same-name/different-content upload through to replace the old rows.)
    reload = False
    try:
        rs = iris.sql.exec("SELECT COUNT(*) FROM Embedding.Clinical WHERE PDF = ?", pSlug)
        for row in rs:
            reload = (row[0] or 0) > 0
            break
    except Exception:
        reload = False

    if reload:
        # Deleting then re-inserting against a LIVE HNSW index can raise during
        # the INSERT, so drop the index first, swap the rows, then rebuild it.
        try:
            iris.sql.exec("DROP INDEX HNSWIndex ON TABLE Embedding.Clinical")
        except Exception:
            pass  # no index yet -> nothing to drop
        # A DELETE that matches no rows returns SQLCODE 100, which iris.sql.exec
        # surfaces as an (empty-message) SQLError -- not a real error.
        try:
            iris.sql.exec("DELETE FROM Embedding.Clinical WHERE PDF = ?", pSlug)
        except Exception:
            pass
    else:
        # Fresh load: ensure the index exists up front (incremental maintenance
        # on insert is fine; it's only delete+reinsert that's problematic).
        create_hnsw()

    # 3) Load chunks.
    with open(pChunksPath, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    insert_sql = (
        "INSERT INTO Embedding.Clinical (Description, Length, Name, Patient, VisitDate, PDF, Hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    inserted = 0
    for chunk in chunks:
        text_val = chunk.get("text", "")
        if not text_val:
            continue
        iris.sql.exec(
            insert_sql,
            text_val,
            chunk.get("tokens", 0),
            chunk.get("heading", ""),
            chunk.get("patient", ""),
            chunk.get("visitdate", ""),
            chunk.get("pdf", "") or pSlug,
            pHash,
        )
        inserted += 1

    # 4) On a re-load we dropped the index above; rebuild it now that the new
    #    rows are in (a bulk build avoids the live delete+reinsert hazard).
    if reload:
        create_hnsw()

    return inserted
}

}
