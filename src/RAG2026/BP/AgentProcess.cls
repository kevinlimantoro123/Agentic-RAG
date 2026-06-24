Include Ensemble

/// Agentic RAG loop, native to IRIS Interoperability. This is the ObjectScript port
/// of rag_tool/agent.py:run_agent. Each turn it asks the LLM operation what to do;
/// if the LLM returns tool_calls it dispatches each to its own business operation
/// (Retrieve / Guideline) so every tool call is a traced interoperability message.
Class RAG2026.BP.AgentProcess Extends Ens.BusinessProcess
{

Parameter SETTINGS = "MaxIterations:Basic,DefaultTopK:Basic";

/// Max LLM<->tool iterations before giving up.
Property MaxIterations As %Integer [ InitialExpression = 10 ];

/// Default top-k when the caller / LLM does not specify one.
Property DefaultTopK As %Integer [ InitialExpression = 5 ];

Method OnRequest(pRequest As RAG2026.Msg.QueryRequest, Output pResponse As RAG2026.Msg.QueryResponse) As %Status
{
    set tSC = $$$OK
    try {
        set pResponse = ##class(RAG2026.Msg.QueryResponse).%New()

        set tMaxIter = ..MaxIterations
        if (pRequest.MaxIterations > 0) { set tMaxIter = pRequest.MaxIterations }
        set tTopK = ..DefaultTopK
        if (pRequest.TopK > 0) { set tTopK = pRequest.TopK }

        // ----- seed the conversation -----
        set tMessages = []
        set tSys = {}
        set tSys.role = "system"
        set tSys.content = ..SystemPrompt()
        do tMessages.%Push(tSys)

        set tCtx = {}
        set tCtx.role = "system"
        set tCtx.content = ..ContextNote(pRequest)
        do tMessages.%Push(tCtx)

        set tUser = {}
        set tUser.role = "user"
        set tUser.content = pRequest.Question
        do tMessages.%Push(tUser)

        set tToolsJSON = ..BuildTools().%ToJSON()
        set tToolLog = []
        set tAnswered = 0

        for tIter = 1:1:tMaxIter {
            // ----- ask the model -----
            set tLLMReq = ##class(RAG2026.Msg.LLMRequest).%New()
            set tLLMReq.MessagesJSON = tMessages.%ToJSON()
            set tLLMReq.ToolsJSON = tToolsJSON
            $$$ThrowOnError(..SendRequestSync("LLM Operation", tLLMReq, .tLLMResp))

            // ----- record the assistant turn -----
            set tAsst = {}
            set tAsst.role = "assistant"
            set tAsst.content = tLLMResp.Content
            if (tLLMResp.ToolCallsJSON '= "") {
                set tAsst."tool_calls" = [].%FromJSON(tLLMResp.ToolCallsJSON)
            }
            do tMessages.%Push(tAsst)

            // ----- no tools => final answer -----
            if (tLLMResp.ToolCallsJSON = "") {
                set pResponse.Answer = tLLMResp.Content
                set tAnswered = 1
                quit
            }

            // ----- dispatch every requested tool call -----
            set tCalls = [].%FromJSON(tLLMResp.ToolCallsJSON)
            set tIt = tCalls.%GetIterator()
            while tIt.%GetNext(.tKey, .tCall) {
                set tCallId = tCall.id
                set tFnName = tCall."function".name
                set tArgs = {}.%FromJSON(tCall."function".arguments)

                set tResultJSON = ..Dispatch(tFnName, tArgs, pRequest, tTopK)

                // append to the UI tool log
                set tLog = {}
                set tLog.tool = tFnName
                set tLog.args = tArgs
                set tLog.result = [].%FromJSON(tResultJSON)
                do tToolLog.%Push(tLog)

                // feed the result back to the model
                set tToolMsg = {}
                set tToolMsg.role = "tool"
                set tToolMsg."tool_call_id" = tCallId
                set tToolMsg.content = tResultJSON
                do tMessages.%Push(tToolMsg)
            }
        }

        if ('tAnswered) {
            set pResponse.Answer = "Maximum reasoning steps reached without a conclusive answer."
        }
        set pResponse.ToolLog = tToolLog.%ToJSON()
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

/// Route one LLM tool call to its business operation; returns the result JSON string.
Method Dispatch(pFnName As %String, pArgs As %DynamicObject, pRequest As RAG2026.Msg.QueryRequest, pTopK As %Integer) As %String
{
    if (pFnName = "retrieve_patient_records") {
        set tReq = ##class(RAG2026.Msg.RetrieveRequest).%New()
        set tReq.Query = pArgs.query
        set tReq.Pdf = $select(pArgs.pdf'="":pArgs.pdf, 1:pRequest.Pdf)
        set tReq.TopK = $select(+pArgs."top_k">0:pArgs."top_k", 1:pTopK)
        set tReq.Patient = $select(pArgs.patient'="":pArgs.patient, 1:pRequest.Patient)
        set tReq.VisitDate = $select(pArgs."visit_date"'="":pArgs."visit_date", 1:pRequest.VisitDate)
        set tSC = ..SendRequestSync("Retrieve Operation", tReq, .tResp)
        if $$$ISERR(tSC) { return "[{""error"":""retrieve_patient_records failed""}]" }
        return tResp.ResultsJSON
    }
    if (pFnName = "guideline_search") {
        set tReq = ##class(RAG2026.Msg.GuidelineRequest).%New()
        set tReq.Query = pArgs.query
        set tReq.Resource = pArgs.resource
        set tReq.MaxResults = $select(+pArgs."max_results">0:pArgs."max_results", 1:3)
        set tSC = ..SendRequestSync("Guideline Operation", tReq, .tResp)
        if $$$ISERR(tSC) { return "[{""error"":""guideline_search failed""}]" }
        return tResp.ResultsJSON
    }
    return "[{""error"":""Unknown tool: "_pFnName_"""}]"
}

/// The agent's system prompt (kept in sync with rag_tool/agent.py:SYSTEM_PROMPT).
Method SystemPrompt() As %String
{
    set p = "You are a careful clinical AI assistant helping clinicians answer medical questions."_$c(10,10)
    set p = p_"You have access to two tools:"_$c(10)
    set p = p_"- retrieve_patient_records: searches the clinical notes database using HNSW vector search"_$c(10)
    set p = p_"- guideline_search: fetches evidence-based guidelines from ACE, NICE, NDF, HSA, FDA, NIH, or CDC"_$c(10,10)
    set p = p_"For each question:"_$c(10)
    set p = p_"1. Call retrieve_patient_records to fetch relevant patient notes from the database."_$c(10)
    set p = p_"2. Call guideline_search on the most appropriate authoritative source for evidence-based context."_$c(10)
    set p = p_"3. You may call tools multiple times with refined queries if the initial results are insufficient."_$c(10)
    set p = p_"4. When you have enough information, synthesise a clear, well-cited answer."_$c(10,10)
    set p = p_"Cite patient records as [P1], [P2], ... and guideline snippets as [G1], [G2], ..."_$c(10)
    set p = p_"If the combined data is still insufficient, say so explicitly."
    quit p
}

/// Per-request context note (active doc + filters), mirroring agent.py.
Method ContextNote(pRequest As RAG2026.Msg.QueryRequest) As %String
{
    set n = "Active document: "_$select(pRequest.Pdf'="":pRequest.Pdf, 1:"none")
    if (pRequest.Patient '= "") { set n = n_" | Patient filter: "_pRequest.Patient }
    if (pRequest.VisitDate '= "") { set n = n_" | Date filter: "_pRequest.VisitDate }
    if (pRequest.Resource '= "") {
        set n = n_" | Preferred guideline source: "_pRequest.Resource_" (prefer this source for guideline_search unless another is clearly more appropriate)"
    }
    quit n
}

/// Build the OpenAI tool (function) schemas as a %DynamicArray.
Method BuildTools() As %DynamicArray
{
    set tools = []

    // ---- retrieve_patient_records ----
    set f1 = {}
    set f1.name = "retrieve_patient_records"
    set f1.description = "Semantic search over the clinical notes database using HNSW vector similarity. Returns matching records with visit date and clinical text."
    set f1props = {}
    set f1props.query = {"type":"string","description":"Natural-language search query"}
    set f1props.pdf = {"type":"string","description":"Document/PDF slug to search within"}
    set f1props.patient = {"type":"string","description":"Patient name substring filter (optional)"}
    set f1props."visit_date" = {"type":"string","description":"Date filter: YYYY, YYYY-MM, or YYYY-MM-DD (optional)"}
    set f1props."top_k" = {"type":"integer","description":"Maximum records to return (default 5)"}
    set f1params = {"type":"object"}
    set f1params.properties = f1props
    set f1params.required = ["query","pdf"]
    set f1.parameters = f1params
    set t1 = {"type":"function"}
    set t1."function" = f1
    do tools.%Push(t1)

    // ---- guideline_search ----
    set f2 = {}
    set f2.name = "guideline_search"
    set f2.description = "Fetch medication guidelines, dosing, or safety information from an authoritative clinical resource. Choose the most relevant source for the question."
    set f2props = {}
    set f2props.query = {"type":"string"}
    set f2props.resource = {"type":"string","enum":["ACE","NICE","NDF","HSA","FDA","NIH","CDC"],"description":"Authoritative source to query"}
    set f2props."max_results" = {"type":"integer"}
    set f2params = {"type":"object"}
    set f2params.properties = f2props
    set f2params.required = ["query","resource"]
    set f2.parameters = f2params
    set t2 = {"type":"function"}
    set t2."function" = f2
    do tools.%Push(t2)

    quit tools
}

Storage Default
{
<Data name="AgentProcessDefaultData">
<Subscript>"AgentProcess"</Subscript>
<Value name="1">
<Value>MaxIterations</Value>
</Value>
<Value name="2">
<Value>DefaultTopK</Value>
</Value>
</Data>
<DefaultData>AgentProcessDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
