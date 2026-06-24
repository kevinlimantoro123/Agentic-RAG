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
  <Route Url="/pdfs" Method="GET" Call="Pdfs"/>
  <Route Url="/patients" Method="GET" Call="Patients"/>
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

/// GET /pdfs -> {"pdfs":["demo", ...]}  (distinct PDF slugs in Embedding.Clinical)
ClassMethod Pdfs() As %Status
{
    try {
        set tArr = []
        set tRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT DISTINCT PDF FROM Embedding.Clinical WHERE PDF IS NOT NULL AND PDF <> '' ORDER BY PDF")
        while tRS.%Next() {
            set tVal = tRS.%Get("PDF")
            if (tVal '= "") { do tArr.%Push(tVal) }
        }
        set tOut = {}
        set tOut.pdfs = tArr
        set %response.ContentType = "application/json"
        write tOut.%ToJSON()
    } catch ex {
        do ..WriteError(ex)
    }
    quit $$$OK
}

/// GET /patients?pdf=demo -> {"patients":["Madam A", ...]}
ClassMethod Patients() As %Status
{
    try {
        set tPdf = %request.Get("pdf")
        set tArr = []
        if (tPdf '= "") {
            set tRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT DISTINCT Patient FROM Embedding.Clinical WHERE PDF = ? AND Patient IS NOT NULL AND Patient <> '' ORDER BY Patient", tPdf)
        } else {
            set tRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT DISTINCT Patient FROM Embedding.Clinical WHERE Patient IS NOT NULL AND Patient <> '' ORDER BY Patient")
        }
        while tRS.%Next() {
            set tVal = tRS.%Get("Patient")
            if (tVal '= "") { do tArr.%Push(tVal) }
        }
        set tOut = {}
        set tOut.patients = tArr
        set %response.ContentType = "application/json"
        write tOut.%ToJSON()
    } catch ex {
        do ..WriteError(ex)
    }
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
