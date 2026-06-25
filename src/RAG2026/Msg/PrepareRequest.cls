/// Request to RAG2026.BO.PrepareOperation. The operation writes the PDF to the
/// shared WorkDir and asks the extractor sidecar to extract+clean+chunk it.
Class RAG2026.Msg.PrepareRequest Extends Ens.Request
{

Property Slug As %String(MAXLEN = 200);

Property PdfBase64 As %String(MAXLEN = "");

Storage Default
{
<Data name="PrepareRequestDefaultData">
<Subscript>"PrepareRequest"</Subscript>
<Value name="1">
<Value>Slug</Value>
</Value>
<Value name="2">
<Value>PdfBase64</Value>
</Value>
</Data>
<DefaultData>PrepareRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
