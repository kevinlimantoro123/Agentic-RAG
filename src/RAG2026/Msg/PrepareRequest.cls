/// Request to RAG2026.BO.PrepareOperation. The operation writes the PDF to the
/// shared WorkDir and asks the extractor sidecar to extract+clean+chunk it.
Class RAG2026.Msg.PrepareRequest Extends Ens.Request
{

Property Slug As %String(MAXLEN = 200);

Property PdfBase64 As %String(MAXLEN = "");

}
