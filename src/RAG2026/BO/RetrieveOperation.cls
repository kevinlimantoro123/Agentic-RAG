Include Ensemble

/// Retrieval business operation: HNSW vector search over Embedding.Clinical using
/// server-side OpenAI embeddings (EMBEDDING(... , 'openai-embedding-config')).
/// This is the native port of rag_tool/test_rag.py:retrieve_text_chunks, run via
/// the embedded-Python iris.sql API (no SQLAlchemy, no torch).
Class RAG2026.BO.RetrieveOperation Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Parameter SETTINGS = "EmbeddingConfig:Basic";

/// Name of the registered %Embedding.Config used by Embedding.Clinical.
Property EmbeddingConfig As %String [ InitialExpression = "openai-embedding-config" ];

XData MessageMap
{
<MapItems>
  <MapItem MessageType="RAG2026.Msg.RetrieveRequest">
    <Method>OnRetrieve</Method>
  </MapItem>
</MapItems>
}

Method OnRetrieve(pRequest As RAG2026.Msg.RetrieveRequest, Output pResponse As RAG2026.Msg.RetrieveResponse) As %Status
{
    set tSC = $$$OK
    set pResponse = ##class(RAG2026.Msg.RetrieveResponse).%New()
    try {
        set pResponse.ResultsJSON = ..Search(pRequest.Query, pRequest.Pdf, pRequest.Patient, pRequest.VisitDate, pRequest.TopK, ..EmbeddingConfig)
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method Search(pQuery As %String, pPdf As %String, pPatient As %String, pVisitDate As %String, pTopK As %Integer, pConfig As %String) As %String [ Language = python ]
{
    import iris, json, re

    query = (pQuery or "").strip()
    try:
        topk = int(pTopK)
    except Exception:
        topk = 5
    if topk <= 0:
        topk = 5

    filters = ["PDF = ?"]
    params = [pPdf]

    if pPatient:
        filters.append("LOWER(Patient) LIKE ?")
        params.append("%" + pPatient.lower() + "%")

    if pVisitDate:
        n = len(pVisitDate)
        if n == 4:                       # YYYY
            filters.append("VisitDate LIKE ?"); params.append(pVisitDate + "-%")
        elif n == 7:                     # YYYY-MM
            filters.append("VisitDate LIKE ?"); params.append(pVisitDate + "%")
        else:                            # YYYY-MM-DD
            filters.append("VisitDate = ?"); params.append(pVisitDate)

    where = "WHERE " + " AND ".join(filters)

    if query:
        # Plain TOP-k ORDER BY VECTOR_DOT_PRODUCT so the optimizer is eligible to
        # use the HNSW index. Embedding is generated server-side by IRIS.
        order = "ORDER BY VECTOR_DOT_PRODUCT(DescriptionEmbedding, EMBEDDING(?, '" + pConfig + "')) DESC"
        params.append(query)
    else:
        # Empty query string is a fatal error for EMBEDDING(); fall back to recency.
        order = "ORDER BY VisitDate DESC"

    # Read the LONGVARCHAR via SUBSTRING (CAST is not allowed on stream fields, SQLCODE -37)
    # so iris.sql returns plain text instead of a stream reference.
    sql = "SELECT TOP " + str(topk) + " VisitDate, SUBSTRING(Description, 1, 32000) FROM Embedding.Clinical " + where + " " + order

    rs = iris.sql.exec(sql, *params)

    seen, out = set(), []
    for row in rs:
        date_val, raw = row[0], row[1]
        if raw is None:
            continue
        if not isinstance(raw, str):
            # LONGVARCHAR comes back as a %Stream.GlobalCharacter object whose
            # str() is just the OID. Read its characters via the IRIS stream API
            # (Read() is capital-R; the file-like read() does not exist).
            try:
                parts = []
                raw.Rewind()
                while not raw.AtEnd:
                    parts.append(raw.Read(16000))
                raw = "".join(parts)
            except Exception:
                raw = str(raw)
        if not raw:
            continue
        txt = raw.encode("ascii", "ignore").decode("ascii")
        norm = re.sub(r"\s+", " ", txt).strip()
        key = (str(date_val), norm.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "label": "P" + str(len(out) + 1),
            "date": str(date_val) if date_val is not None else "",
            "text": norm,
        })
        if len(out) >= topk:
            break

    return json.dumps(out)
}

}
