/// Request to RAG2026.BO.GuidelineOperation (Tavily web search over an authoritative domain).
Class RAG2026.Msg.GuidelineRequest Extends Ens.Request
{

Property Query As %String(MAXLEN = "");

/// One of ACE, NICE, NDF, HSA, FDA, NIH, CDC.
Property Resource As %String(MAXLEN = 20);

Property MaxResults As %Integer [ InitialExpression = 3 ];

Storage Default
{
<Data name="GuidelineRequestDefaultData">
<Subscript>"GuidelineRequest"</Subscript>
<Value name="1">
<Value>Query</Value>
</Value>
<Value name="2">
<Value>Resource</Value>
</Value>
<Value name="3">
<Value>MaxResults</Value>
</Value>
</Data>
<DefaultData>GuidelineRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
