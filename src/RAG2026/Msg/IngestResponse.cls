/// Final ingestion result returned by RAG2026.BP.IngestProcess.
Class RAG2026.Msg.IngestResponse Extends Ens.Response
{

Property Slug As %String(MAXLEN = 200);

Property RowsInserted As %Integer [ InitialExpression = 0 ];

Property ChunksPath As %String(MAXLEN = 500);

/// JSON blob of sidecar extraction stats.
Property Stats As %String(MAXLEN = "");

}
