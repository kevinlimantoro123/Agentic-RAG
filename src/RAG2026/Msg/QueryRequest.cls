/// Inbound request for the agentic query path. Created by RAG2026.BS.QueryService
/// from the REST body and sent to RAG2026.BP.AgentProcess.
Class RAG2026.Msg.QueryRequest Extends Ens.Request
{

/// The clinician's natural-language question.
Property Question As %String(MAXLEN = "");

/// PDF / document slug to search within (maps to Embedding.Clinical.PDF).
Property Pdf As %String(MAXLEN = 200);

/// Optional patient-name substring filter.
Property Patient As %String(MAXLEN = 200);

/// Optional visit-date filter: YYYY, YYYY-MM, or YYYY-MM-DD.
Property VisitDate As %String(MAXLEN = 50);

/// Preferred guideline source (ACE, NICE, NDF, HSA, FDA, NIH, CDC).
Property Resource As %String(MAXLEN = 20);

/// Max records per retrieval (0 = use process default).
Property TopK As %Integer [ InitialExpression = 0 ];

/// Max agent reasoning iterations (0 = use process default).
Property MaxIterations As %Integer [ InitialExpression = 0 ];

Storage Default
{
<Data name="QueryRequestDefaultData">
<Subscript>"QueryRequest"</Subscript>
<Value name="1">
<Value>Question</Value>
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
<Value>Resource</Value>
</Value>
<Value name="6">
<Value>TopK</Value>
</Value>
<Value name="7">
<Value>MaxIterations</Value>
</Value>
</Data>
<DefaultData>QueryRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
