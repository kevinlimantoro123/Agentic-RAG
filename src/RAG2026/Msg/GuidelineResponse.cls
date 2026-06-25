/// Response from RAG2026.BO.GuidelineOperation.
Class RAG2026.Msg.GuidelineResponse Extends Ens.Response
{

/// JSON array of {label, text, source} snippets.
Property ResultsJSON As %String(MAXLEN = "");

Storage Default
{
<Data name="GuidelineResponseDefaultData">
<Subscript>"GuidelineResponse"</Subscript>
<Value name="1">
<Value>ResultsJSON</Value>
</Value>
</Data>
<DefaultData>GuidelineResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
