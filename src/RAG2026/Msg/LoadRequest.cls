/// Request to RAG2026.BO.LoadOperation. Loads a chunks.json into Embedding.Clinical
/// (server-side OpenAI embeddings + HNSW index).
Class RAG2026.Msg.LoadRequest Extends Ens.Request
{

Property Slug As %String(MAXLEN = 200);

Property ChunksPath As %String(MAXLEN = 500);

/// SHA-256 hex digest of the raw PDF bytes; written to Embedding.Clinical.Hash.
Property Hash As %String(MAXLEN = 64);

Storage Default
{
<Data name="LoadRequestDefaultData">
<Subscript>"LoadRequest"</Subscript>
<Value name="1">
<Value>Slug</Value>
</Value>
<Value name="2">
<Value>ChunksPath</Value>
</Value>
<Value name="3">
<Value>Hash</Value>
</Value>
</Data>
<DefaultData>LoadRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
