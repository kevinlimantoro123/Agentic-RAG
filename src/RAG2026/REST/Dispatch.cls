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
  <Route Url="/ingest/status" Method="GET" Call="IngestStatus"/>
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
            set tVal = tRS.%GetData(1)
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
            set tVal = tRS.%GetData(1)
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

/// POST /ingest -> queues the job, runs it in a background process, returns a job id.
ClassMethod Ingest() As %Status
{
    try {
        set tBody = {}.%FromJSON(%request.Content)

        // Duplicate guard: if this slug is already loaded, skip re-ingesting it
        // entirely (avoids re-running extraction and re-touching the vector store).
        set tCount = 0
        try {
            set tDupRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT COUNT(*) FROM Embedding.Clinical WHERE PDF = ?", tBody.slug)
            if tDupRS.%Next() { set tCount = +tDupRS.%GetData(1) }
        } catch eDup {
            set tCount = 0  // table doesn't exist yet -> not a duplicate
        }
        if (tCount > 0) {
            set tOut = {}
            set tOut.status = "Duplicate"
            set tOut.slug = tBody.slug
            set tOut."rows_inserted" = tCount
            set %response.ContentType = "application/json"
            write tOut.%ToJSON()
            return $$$OK
        }

        set tJob = ##class(RAG2026.Data.IngestJob).%New()
        set tJob.JobId = ..NewJobId()
        set tJob.Slug = tBody.slug
        set tJob.PdfBase64 = tBody."pdf_base64"
        set tJob.Status = "Queued"
        $$$ThrowOnError(tJob.%Save())

        // Run in the background so the HTTP request returns immediately
        // (no Web Gateway response timeout on long extractions).
        job ##class(RAG2026.REST.Dispatch).RunIngestJob(tJob.JobId)

        set tOut = {}
        set tOut."job_id" = tJob.JobId
        set tOut.status = "Queued"
        set %response.ContentType = "application/json"
        write tOut.%ToJSON()
    } catch ex {
        do ..WriteError(ex)
    }
    quit $$$OK
}

/// GET /ingest/status?id=... -> {status, slug, rows_inserted, error?}
ClassMethod IngestStatus() As %Status
{
    set tJob = ##class(RAG2026.Data.IngestJob).OpenByJobId(%request.Get("id"))
    set tOut = {}
    if (tJob = "") {
        set tOut.status = "NotFound"
    } else {
        set tOut."job_id" = tJob.JobId
        set tOut.slug = tJob.Slug
        set tOut.status = tJob.Status
        set tOut."rows_inserted" = tJob.RowsInserted
        if (tJob.Error '= "") { set tOut.error = tJob.Error }
    }
    set %response.ContentType = "application/json"
    write tOut.%ToJSON()
    quit $$$OK
}

/// Background worker: runs the (synchronous) ingest off the web request and records status.
ClassMethod RunIngestJob(pJobId As %String)
{
    do ##class(RAG2026.Data.IngestJob).Mark(pJobId, "Running")
    set tJob = ##class(RAG2026.Data.IngestJob).OpenByJobId(pJobId)
    if (tJob = "") quit
    try {
        set tReq = ##class(RAG2026.Msg.IngestRequest).%New()
        set tReq.Slug = tJob.Slug
        set tReq.PdfBase64 = tJob.PdfBase64
        $$$ThrowOnError(##class(Ens.Director).CreateBusinessService("Ingest Service", .tService))
        $$$ThrowOnError(tService.ProcessInput(tReq, .tResp))
        do ##class(RAG2026.Data.IngestJob).Mark(pJobId, "Done", tResp.RowsInserted)
        // free the stored PDF payload
        set tJob = ##class(RAG2026.Data.IngestJob).OpenByJobId(pJobId)
        if (tJob '= "") { set tJob.PdfBase64 = "" do tJob.%Save() }
    } catch ex {
        do ##class(RAG2026.Data.IngestJob).Mark(pJobId, "Error", 0, ex.DisplayString())
    }
}

ClassMethod NewJobId() As %String
{
    quit $TRANSLATE($SYSTEM.Util.CreateGUID(), "-", "")
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
