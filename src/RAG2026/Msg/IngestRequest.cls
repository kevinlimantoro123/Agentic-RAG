/// Inbound request for the ingestion path. Created by RAG2026.BS.IngestService
/// from the REST body and sent to RAG2026.BP.IngestProcess.
Class RAG2026.Msg.IngestRequest Extends Ens.Request
{

/// Document slug (used as the work-dir name and the Embedding.Clinical.PDF value).
Property Slug As %String(MAXLEN = 200);

/// Base64-encoded PDF bytes. (For very large PDFs, drop the file into the
/// shared WorkDir instead and leave this empty.)
Property PdfBase64 As %String(MAXLEN = "");

/// SHA-256 hex digest of the raw PDF bytes. Used for content-based dedup and
/// stored on every chunk row in Embedding.Clinical.
Property Hash As %String(MAXLEN = 64);

Storage Default
{
<Data name="IngestRequestDefaultData">
<Subscript>"IngestRequest"</Subscript>
<Value name="1">
<Value>Slug</Value>
</Value>
<Value name="2">
<Value>PdfBase64</Value>
</Value>
<Value name="3">
<Value>Hash</Value>
</Value>
</Data>
<DefaultData>IngestRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
