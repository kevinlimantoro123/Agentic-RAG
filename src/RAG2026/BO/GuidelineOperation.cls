Include Ensemble

/// Guideline business operation: authoritative web search via Tavily, restricted to
/// one approved domain. Native port of rag_tool/test_rag.py:guideline_search.
/// Light Python only (langchain_tavily) -> safe in-process.
Class RAG2026.BO.GuidelineOperation Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Parameter SETTINGS = "TavilyCredentials:Tavily:credentialsSelector";

/// Ens.Config.Credentials ID whose Password holds the Tavily API key.
Property TavilyCredentials As %String;

XData MessageMap
{
<MapItems>
  <MapItem MessageType="RAG2026.Msg.GuidelineRequest">
    <Method>OnGuideline</Method>
  </MapItem>
</MapItems>
}

Method OnGuideline(pRequest As RAG2026.Msg.GuidelineRequest, Output pResponse As RAG2026.Msg.GuidelineResponse) As %Status
{
    set tSC = $$$OK
    set pResponse = ##class(RAG2026.Msg.GuidelineResponse).%New()
    try {
        set tMax = pRequest.MaxResults
        if (tMax <= 0) { set tMax = 3 }
        set pResponse.ResultsJSON = ..WebSearch(pRequest.Query, pRequest.Resource, tMax)
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
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
    import os
    key = self.GetAPIKey(self.TavilyCredentials)
    if key:
        os.environ["TAVILY_API_KEY"] = key
}

Method GetAPIKey(pCredentialsID As %String) As %String [ Private ]
{
    set tSC = ##class(Ens.Config.Credentials).GetCredentialsObj(.tCreds, $CLASSNAME(), "Ens.Config.Credentials", pCredentialsID)
    if $$$ISOK(tSC) {
        return tCreds.Password
    }
    return ""
}

Method WebSearch(pQuery As %String, pResource As %String, pMaxResults As %Integer) As %String [ Language = python ]
{
    import json, re
    from langchain_tavily import TavilySearch

    domains = {
        "ACE": "ace-hta.gov.sg",
        "NICE": "nice.org.uk",
        "NDF": "ndf.gov.sg",
        "HSA": "hsa.gov.sg",
        "FDA": "fda.gov",
        "NIH": "nih.gov",
        "CDC": "cdc.gov",
    }

    resource = (pResource or "").upper()
    if resource not in domains:
        return json.dumps([{"error": "Unknown resource " + str(pResource)}])

    try:
        maxr = int(pMaxResults)
    except Exception:
        maxr = 3
    if maxr <= 0:
        maxr = 3

    tool = TavilySearch(max_results=maxr, include_domains=[domains[resource]], include_raw_content=True)
    resp = tool.invoke({"query": pQuery})

    if isinstance(resp, dict) and "results" in resp:
        raw_hits = resp["results"]
    elif isinstance(resp, list):
        raw_hits = resp
    else:
        raw_hits = [resp]

    results, idx = [], 0
    for hit in raw_hits[:maxr]:
        if isinstance(hit, dict):
            content = hit.get("content") or hit.get("raw_content") or ""
            source = hit.get("url", "n/a")
        else:
            content = str(hit)
            source = "n/a"
        text = (content or "").strip()
        if not text:
            continue
        idx += 1
        snippet = re.sub(r"\s+", " ", text)[:500]
        results.append({"label": "G" + str(idx), "text": snippet, "source": source})

    return json.dumps(results)
}

}
