/// Response from RAG2026.BO.PrepareOperation. Populated via %JSONImport, so the
/// %JSONFIELDNAME values must match the keys produced by Prepare().
Class RAG2026.Msg.PrepareResponse Extends (Ens.Response, %JSON.Adaptor)
{

Property Slug As %String(%JSONFIELDNAME = "slug", MAXLEN = 200);

/// Absolute path to the chunks.json produced by the sidecar.
Property ChunksPath As %String(%JSONFIELDNAME = "chunksPath", MAXLEN = 500);

/// JSON blob of extraction stats.
Property Stats As %String(%JSONFIELDNAME = "stats", MAXLEN = "");

Storage Default
{
<Data name="PrepareResponseDefaultData">
<Subscript>"PrepareResponse"</Subscript>
<Value name="1">
<Value>Slug</Value>
</Value>
<Value name="2">
<Value>ChunksPath</Value>
</Value>
<Value name="3">
<Value>Stats</Value>
</Value>
</Data>
<DefaultData>PrepareResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
