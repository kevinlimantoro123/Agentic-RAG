/// Final answer + tool-call log returned by RAG2026.BP.AgentProcess.
Class RAG2026.Msg.QueryResponse Extends Ens.Response
{

/// Synthesised, cited answer.
Property Answer As %String(MAXLEN = "");

/// JSON array of {tool, args, result} entries for UI display.
Property ToolLog As %String(MAXLEN = "");

Storage Default
{
<Data name="QueryResponseDefaultData">
<Subscript>"QueryResponse"</Subscript>
<Value name="1">
<Value>Answer</Value>
</Value>
<Value name="2">
<Value>ToolLog</Value>
</Value>
</Data>
<DefaultData>QueryResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
