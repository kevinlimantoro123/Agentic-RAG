/// Response from RAG2026.BO.LLMOperation. Populated via %JSONImport so the
/// %JSONFIELDNAME values must match the keys produced by CallLLM().
Class RAG2026.Msg.LLMResponse Extends (Ens.Response, %JSON.Adaptor)
{

/// Assistant message text (may be empty when only tool calls are returned).
Property Content As %String(%JSONFIELDNAME = "content", MAXLEN = "");

/// OpenAI finish_reason.
Property FinishReason As %String(%JSONFIELDNAME = "finishReason", MAXLEN = 100);

/// JSON array of tool_calls [{id,type,function:{name,arguments}}]. Empty = none.
Property ToolCallsJSON As %String(%JSONFIELDNAME = "toolCalls", MAXLEN = "");

Storage Default
{
<Data name="LLMResponseDefaultData">
<Subscript>"LLMResponse"</Subscript>
<Value name="1">
<Value>Content</Value>
</Value>
<Value name="2">
<Value>FinishReason</Value>
</Value>
<Value name="3">
<Value>ToolCallsJSON</Value>
</Value>
</Data>
<DefaultData>LLMResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
