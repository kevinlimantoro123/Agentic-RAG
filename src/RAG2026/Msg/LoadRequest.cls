/// Request to RAG2026.BO.LoadOperation. Loads a chunks.json into Embedding.Clinical
/// (server-side OpenAI embeddings + HNSW index).
Class RAG2026.Msg.LoadRequest Extends Ens.Request
{

Property Slug As %String(MAXLEN = 200);

Property ChunksPath As %String(MAXLEN = 500);

}
