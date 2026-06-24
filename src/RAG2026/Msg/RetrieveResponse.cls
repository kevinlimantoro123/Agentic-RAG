/// Response from RAG2026.BO.RetrieveOperation.
Class RAG2026.Msg.RetrieveResponse Extends Ens.Response
{

/// JSON array of {label, date, text} records.
Property ResultsJSON As %String(MAXLEN = "");

Storage Default
{
<Data name="RetrieveResponseDefaultData">
<Subscript>"RetrieveResponse"</Subscript>
<Value name="1">
<Value>ResultsJSON</Value>
</Value>
</Data>
<DefaultData>RetrieveResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
