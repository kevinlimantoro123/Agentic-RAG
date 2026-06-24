/// Request to RAG2026.BO.LoadOperation. Loads a chunks.json into Embedding.Clinical
/// (server-side OpenAI embeddings + HNSW index).
Class RAG2026.Msg.LoadRequest Extends Ens.Request
{

Property Slug As %String(MAXLEN = 200);

Property ChunksPath As %String(MAXLEN = 500);

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
</Data>
<DefaultData>LoadRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
