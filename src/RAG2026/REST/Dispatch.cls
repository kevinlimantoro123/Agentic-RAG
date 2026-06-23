Include Ensemble

/// HTTP front door for the production. Register this class as the dispatch class of
/// a web application (e.g. /csp/rag2026). Each handler builds a typed message and
/// pushes it into the production via an adapterless business service.
///
///   POST /query    {"question","pdf","patient","visit_date","resource","top_k"}
///   POST /ingest   {"slug","pdf_base64"}
///   GET  /health
Class RAG2026.REST.Dispatch Extends %CSP.REST
{

Parameter CHARSET = "utf-8";

XData UrlMap [ XMLNamespace = "http://www.intersystems.com/urlmap" ]
{
<Routes>
  <Route Url="/health" Method="GET" Call="Health"/>
  <Route Url="/query" Method="POST" Call="Query"/>
  <Route Url="/ingest" Method="POST" Call="Ingest"/>
</Routes>
}

ClassMethod Health() As %Status
{
    set %response.ContentType = "application/json"
    write "{""status"":""ok""}"
    quit $$$OK
}

ClassMethod Query() As %Status
{
    try {
        set tBody = {}.%FromJSON(%request.Content)

        set tReq = ##class(RAG2026.Msg.QueryRequest).%New()
        set tReq.Question = tBody.question
        set tReq.Pdf = tBody.pdf
        set tReq.Patient = tBody.patient
        set tReq.VisitDate = tBody."visit_date"
        set tReq.Resource = tBody.resource
        if (tBody."top_k" '= "") { set tReq.TopK = tBody."top_k" }

        $$$ThrowOnError(##class(Ens.Director).CreateBusinessService("Query Service", .tService))
        $$$ThrowOnError(tService.ProcessInput(tReq, .tResp))

        set tOut = {}
        set tOut.answer = tResp.Answer
        if (tResp.ToolLog '= "") { set tOut."tool_log" = [].%FromJSON(tResp.ToolLog) }

        set %response.ContentType = "application/json"
        write tOut.%ToJSON()
    } catch ex {
        do ..WriteError(ex)
    }
    quit $$$OK
}

ClassMethod Ingest() As %Status
{
    try {
        set tBody = {}.%FromJSON(%request.Content)

        set tReq = ##class(RAG2026.Msg.IngestRequest).%New()
        set tReq.Slug = tBody.slug
        set tReq.PdfBase64 = tBody."pdf_base64"

        $$$ThrowOnError(##class(Ens.Director).CreateBusinessService("Ingest Service", .tService))
        $$$ThrowOnError(tService.ProcessInput(tReq, .tResp))

        set tOut = {}
        set tOut.slug = tResp.Slug
        set tOut."rows_inserted" = tResp.RowsInserted
        set tOut."chunks_path" = tResp.ChunksPath

        set %response.ContentType = "application/json"
        write tOut.%ToJSON()
    } catch ex {
        do ..WriteError(ex)
    }
    quit $$$OK
}

ClassMethod WriteError(pEx As %Exception.AbstractException)
{
    set %response.Status = "500 Internal Server Error"
    set %response.ContentType = "application/json"
    set tErr = {}
    set tErr.error = pEx.DisplayString()
    write tErr.%ToJSON()
}

}
