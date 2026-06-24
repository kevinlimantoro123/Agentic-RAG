Include Ensemble

/// LLM business operation: relays the chat messages + tool schemas to OpenAI and
/// returns the assistant turn (content + any tool_calls). The agent loop lives in
/// RAG2026.BP.AgentProcess; this operation is a single stateless OpenAI call.
/// 
/// Light Python only (openai) -> safe to run as embedded Python in-process.
Class RAG2026.BO.LLMOperation Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Parameter SETTINGS = "Model:OpenAI,APIKeyCredentials:OpenAI:credentialsSelector";

/// Chat model to use.
Property Model As %String [ InitialExpression = "gpt-4o" ];

/// Ens.Config.Credentials ID whose Password holds the OpenAI API key.
Property APIKeyCredentials As %String;

/// OpenAI client handle.
Property Client As %SYS.Python [ Private ];

XData MessageMap
{
<MapItems>
  <MapItem MessageType="RAG2026.Msg.LLMRequest">
    <Method>OnLLM</Method>
  </MapItem>
</MapItems>
}

Method OnLLM(pRequest As RAG2026.Msg.LLMRequest, Output pResponse As RAG2026.Msg.LLMResponse) As %Status
{
    set tSC = $$$OK
    set pResponse = ##class(RAG2026.Msg.LLMResponse).%New()
    try {
        do pResponse.%JSONImport(..CallLLM(pRequest.MessagesJSON, pRequest.ToolsJSON, ..Model))
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method CallLLM(pMessages As %String, pTools As %String, pModel As %String) As %String [ Language = python ]
{
    import json
    messages = json.loads(pMessages)
    tools = json.loads(pTools) if pTools else None
    kwargs = {"model": pModel or "gpt-4o", "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = self.Client.chat.completions.create(**kwargs)
    m = resp.choices[0].message
    out = {
        "content": m.content or "",
        "finishReason": resp.choices[0].finish_reason or "",
        "toolCalls": "",
    }
    if m.tool_calls:
        out["toolCalls"] = json.dumps([
            {
                "id": t.id,
                "type": "function",
                "function": {"name": t.function.name, "arguments": t.function.arguments},
            }
            for t in m.tool_calls
        ])
    return json.dumps(out)
}

Method OnInit() As %Status
{
    set tSC = $$$OK
    try {
        do ..PyInit()
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method PyInit() [ Language = python ]
{
    from openai import OpenAI
    self.Client = OpenAI(api_key=self.GetAPIKey(self.APIKeyCredentials))
}

Method GetAPIKey(pCredentialsID As %String) As %String [ Private ]
{
    set tSC = ##class(Ens.Config.Credentials).GetCredentialsObj(.tCreds, $CLASSNAME(), "Ens.Config.Credentials", pCredentialsID)
    if $$$ISOK(tSC) {
        return tCreds.Password
    }
    return ""
}

}
