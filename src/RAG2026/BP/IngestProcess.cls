Include Ensemble

/// Ingestion orchestration: Prepare (sidecar extract+clean+chunk) -> Load (into
/// Embedding.Clinical with server-side embeddings + HNSW).
Class RAG2026.BP.IngestProcess Extends Ens.BusinessProcess
{

Method OnRequest(pRequest As RAG2026.Msg.IngestRequest, Output pResponse As RAG2026.Msg.IngestResponse) As %Status
{
    set tSC = $$$OK
    try {
        set pResponse = ##class(RAG2026.Msg.IngestResponse).%New()
        set pResponse.Slug = pRequest.Slug

        // 1) Prepare (out-of-process heavy extraction via the sidecar)
        set tPrep = ##class(RAG2026.Msg.PrepareRequest).%New()
        set tPrep.Slug = pRequest.Slug
        set tPrep.PdfBase64 = pRequest.PdfBase64
        $$$ThrowOnError(..SendRequestSync("Prepare Operation", tPrep, .tPrepResp))
        set pResponse.ChunksPath = tPrepResp.ChunksPath
        set pResponse.Stats = tPrepResp.Stats

        // 2) Load into the vector store (server-side OpenAI embeddings + HNSW)
        set tLoad = ##class(RAG2026.Msg.LoadRequest).%New()
        set tLoad.Slug = pRequest.Slug
        set tLoad.ChunksPath = tPrepResp.ChunksPath
        $$$ThrowOnError(..SendRequestSync("Load Operation", tLoad, .tLoadResp))
        set pResponse.RowsInserted = tLoadResp.RowsInserted
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

}
