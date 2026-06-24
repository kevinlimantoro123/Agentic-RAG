/// Request to RAG2026.BO.LLMOperation. Carries the full OpenAI chat state.
Class RAG2026.Msg.LLMRequest Extends Ens.Request
{

/// JSON array of OpenAI chat messages (system/user/assistant/tool).
Property MessagesJSON As %String(MAXLEN = "");

/// JSON array of OpenAI tool (function) schemas. Empty = no tools.
Property ToolsJSON As %String(MAXLEN = "");

Storage Default
{
<Data name="LLMRequestDefaultData">
<Subscript>"LLMRequest"</Subscript>
<Value name="1">
<Value>MessagesJSON</Value>
</Value>
<Value name="2">
<Value>ToolsJSON</Value>
</Value>
</Data>
<DefaultData>LLMRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
