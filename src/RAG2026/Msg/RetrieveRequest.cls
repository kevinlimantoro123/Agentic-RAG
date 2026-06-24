/// Request to RAG2026.BO.RetrieveOperation (HNSW vector search over Embedding.Clinical).
Class RAG2026.Msg.RetrieveRequest Extends Ens.Request
{

Property Query As %String(MAXLEN = "");

Property Pdf As %String(MAXLEN = 200);

Property Patient As %String(MAXLEN = 200);

Property VisitDate As %String(MAXLEN = 50);

Property TopK As %Integer [ InitialExpression = 5 ];

Storage Default
{
<Data name="RetrieveRequestDefaultData">
<Subscript>"RetrieveRequest"</Subscript>
<Value name="1">
<Value>Query</Value>
</Value>
<Value name="2">
<Value>Pdf</Value>
</Value>
<Value name="3">
<Value>Patient</Value>
</Value>
<Value name="4">
<Value>VisitDate</Value>
</Value>
<Value name="5">
<Value>TopK</Value>
</Value>
</Data>
<DefaultData>RetrieveRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
