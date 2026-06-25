/// Final ingestion result returned by RAG2026.BP.IngestProcess.
Class RAG2026.Msg.IngestResponse Extends Ens.Response
{

Property Slug As %String(MAXLEN = 200);

Property RowsInserted As %Integer [ InitialExpression = 0 ];

Property ChunksPath As %String(MAXLEN = 500);

/// JSON blob of sidecar extraction stats.
Property Stats As %String(MAXLEN = "");

Storage Default
{
<Data name="IngestResponseDefaultData">
<Subscript>"IngestResponse"</Subscript>
<Value name="1">
<Value>Slug</Value>
</Value>
<Value name="2">
<Value>RowsInserted</Value>
</Value>
<Value name="3">
<Value>ChunksPath</Value>
</Value>
<Value name="4">
<Value>Stats</Value>
</Value>
</Data>
<DefaultData>IngestResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
