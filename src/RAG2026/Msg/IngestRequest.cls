/// Inbound request for the ingestion path. Created by RAG2026.BS.IngestService
/// from the REST body and sent to RAG2026.BP.IngestProcess.
Class RAG2026.Msg.IngestRequest Extends Ens.Request
{

/// Document slug (used as the work-dir name and the Embedding.Clinical.PDF value).
Property Slug As %String(MAXLEN = 200);

/// Base64-encoded PDF bytes. (For very large PDFs, drop the file into the
/// shared WorkDir instead and leave this empty.)
Property PdfBase64 As %String(MAXLEN = "");

}
