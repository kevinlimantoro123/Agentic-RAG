/// Tracks an asynchronous ingestion job so the REST layer can return immediately
/// and the UI can poll for progress (avoids Web Gateway response timeouts on long
/// extractions). The PDF payload is stored here only until the job finishes.
Class RAG2026.Data.IngestJob Extends %Persistent
{

Property JobId As %String(MAXLEN = 64);

Property Slug As %String(MAXLEN = 200);

Property PdfBase64 As %String(MAXLEN = "");

Property Status As %String(VALUELIST = ",Queued,Running,Done,Error") [ InitialExpression = "Queued" ];

Property RowsInserted As %Integer [ InitialExpression = 0 ];

Property Error As %String(MAXLEN = "");

Property Created As %TimeStamp [ InitialExpression = {$ZDATETIME($HOROLOG, 3)} ];

Property Updated As %TimeStamp;

Index JobIdIdx On JobId [ Unique ];

/// Open a job by its external JobId (returns "" if not found).
ClassMethod OpenByJobId(pJobId As %String) As RAG2026.Data.IngestJob
{
    if (pJobId = "") quit ""
    if '..JobIdIdxExists(pJobId, .tId) quit ""
    quit ..%OpenId(tId)
}

/// Update status (and optionally rows/error) for a job. No-op if not found.
ClassMethod Mark(pJobId As %String, pStatus As %String, pRows As %Integer = 0, pError As %String = "") As %Status
{
    set tJob = ..OpenByJobId(pJobId)
    if (tJob = "") quit $$$OK
    set tJob.Status = pStatus
    if (pRows > 0) { set tJob.RowsInserted = pRows }
    if (pError '= "") { set tJob.Error = pError }
    set tJob.Updated = $ZDATETIME($HOROLOG, 3)
    quit tJob.%Save()
}

Storage Default
{
<Data name="IngestJobDefaultData">
<Value name="1">
<Value>%%CLASSNAME</Value>
</Value>
<Value name="2">
<Value>JobId</Value>
</Value>
<Value name="3">
<Value>Slug</Value>
</Value>
<Value name="4">
<Value>PdfBase64</Value>
</Value>
<Value name="5">
<Value>Status</Value>
</Value>
<Value name="6">
<Value>RowsInserted</Value>
</Value>
<Value name="7">
<Value>Error</Value>
</Value>
<Value name="8">
<Value>Created</Value>
</Value>
<Value name="9">
<Value>Updated</Value>
</Value>
</Data>
<DataLocation>^RAG2026.Data.IngestJobD</DataLocation>
<DefaultData>IngestJobDefaultData</DefaultData>
<IdLocation>^RAG2026.Data.IngestJobD</IdLocation>
<IndexLocation>^RAG2026.Data.IngestJobI</IndexLocation>
<StreamLocation>^RAG2026.Data.IngestJobS</StreamLocation>
<Type>%Storage.Persistent</Type>
}

}
