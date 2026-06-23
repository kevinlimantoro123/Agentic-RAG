/// Request to RAG2026.BO.GuidelineOperation (Tavily web search over an authoritative domain).
Class RAG2026.Msg.GuidelineRequest Extends Ens.Request
{

Property Query As %String(MAXLEN = "");

/// One of ACE, NICE, NDF, HSA, FDA, NIH, CDC.
Property Resource As %String(MAXLEN = 20);

Property MaxResults As %Integer [ InitialExpression = 3 ];

}
