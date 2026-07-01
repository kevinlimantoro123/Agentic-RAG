Include Ensemble

/// HTTP front door for the production. Register this class as the dispatch class of
/// a web application (e.g. /csp/rag2026). Each handler builds a typed message and
/// pushes it into the production via an adapterless business service.
/// 
///   POST /query    {"question","pdf","patient","visit_date","resource","top_k"}
///   POST /ingest   {"slug","pdf_base64"}
///   GET  /health
///   GET  /dedup    -> {"mode":"Slug|Content"}
///   POST /dedup    {"mode":"Slug|Content"}  toggles the duplicate-detection policy
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
  <Route Url="/ingest/check" Method="GET" Call="IngestCheck"/>
  <Route Url="/ingest/status" Method="GET" Call="IngestStatus"/>
  <Route Url="/dedup" Method="GET" Call="DedupGet"/>
  <Route Url="/dedup" Method="POST" Call="DedupSet"/>
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
        set tHash = ..PdfHash(tBody."pdf_base64")
        set tMode = ..DedupMode()

        // Duplicate guard. Two policies (see DedupMode):
        //   Slug    -> identity is the filename: a duplicate is any upload whose
        //              slug is already loaded.
        //   Content -> a duplicate is only the SAME slug holding the SAME content
        //              (same name + same bytes). Same name + different bytes is NOT a
        //              duplicate -- it falls through and replaces that slug's rows
        //              (safe HNSW reload). A different filename is always allowed,
        //              even if the content is identical to an existing document.
        set tDup = 0, tDupCount = 0, tDupSlug = tBody.slug
        set tSlugCount = ..CountWhere("PDF = ?", tBody.slug)
        if (tMode = "Content") {
            if (tSlugCount > 0) {
                set tSameCount = ..CountWhere2("PDF = ? AND Hash = ?", tBody.slug, tHash)
                if (tSameCount > 0) { set tDup = 1, tDupCount = tSlugCount }
            }
        } else {
            if (tSlugCount > 0) { set tDup = 1, tDupCount = tSlugCount }
        }
        if (tDup) {
            set tOut = {}
            set tOut.status = "Duplicate"
            set tOut.mode = tMode
            set tOut.slug = tDupSlug
            set tOut."rows_inserted" = tDupCount
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
        set tReq.Hash = ..PdfHash(tJob.PdfBase64)
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

/// SHA-256 hex digest of the raw PDF bytes carried in a base64 string. Returns
/// "" when the input is empty or not decodable (treated as "no content hash").
ClassMethod PdfHash(pB64 As %String) As %String [ Language = python ]
{
    import base64, hashlib
    if not pB64:
        return ""
    try:
        raw = base64.b64decode(pB64)
    except Exception:
        return ""
    return hashlib.sha256(raw).hexdigest()
}

/// Current duplicate-detection policy: "Slug" (default) or "Content".
ClassMethod DedupMode() As %String
{
    set tMode = $GET(^RAG2026.Config("DedupMode"), "Slug")
    quit $SELECT(tMode = "Content": "Content", 1: "Slug")
}

/// COUNT(*) from Embedding.Clinical for a single-parameter WHERE clause, tolerant
/// of the table (or Hash column) not existing yet -> returns 0.
ClassMethod CountWhere(pWhere As %String, pArg As %String) As %Integer
{
    set tCount = 0
    try {
        set tRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT COUNT(*) FROM Embedding.Clinical WHERE " _ pWhere, pArg)
        if tRS.%Next() { set tCount = +tRS.%GetData(1) }
    } catch e {
        set tCount = 0
    }
    quit tCount
}

/// COUNT(*) from Embedding.Clinical for a two-parameter WHERE clause, tolerant of
/// the table (or Hash column) not existing yet -> returns 0.
ClassMethod CountWhere2(pWhere As %String, pArg1 As %String, pArg2 As %String) As %Integer
{
    set tCount = 0
    try {
        set tRS = ##class(%SQL.Statement).%ExecDirect(, "SELECT COUNT(*) FROM Embedding.Clinical WHERE " _ pWhere, pArg1, pArg2)
        if tRS.%Next() { set tCount = +tRS.%GetData(1) }
    } catch e {
        set tCount = 0
    }
    quit tCount
}

/// First column of the first row of a single-parameter query, "" on any failure.
ClassMethod FirstValue(pSql As %String, pArg As %String) As %String
{
    set tVal = ""
    try {
        set tRS = ##class(%SQL.Statement).%ExecDirect(, pSql, pArg)
        if tRS.%Next() { set tVal = tRS.%GetData(1) }
    } catch e {
        set tVal = ""
    }
    quit tVal
}

/// GET /ingest/check?slug=<slug>&hash=<sha256hex>
/// Returns what /ingest would do without actually running it:
///   {"action":"new"}                         fresh ingest
///   {"action":"replace","rows":<n>}          slug exists, content differs (Content mode only)
///   {"action":"duplicate","existing_slug":<s>,"rows":<n>}  blocked
ClassMethod IngestCheck() As %Status
{
    set tSlug = %request.Get("slug")
    set tHash = %request.Get("hash")
    set tMode = ..DedupMode()
    set tOut = {}
    set tOut.mode = tMode

    if (tMode = "Content") {
        // Different filename -> always a new document (even if content matches).
        // Same filename -> duplicate if the content is identical, else a replace.
        set tSlugRows = ..CountWhere("PDF = ?", tSlug)
        if (tSlugRows = 0) {
            set tOut.action = "new"
        } else {
            set tSameCount = ..CountWhere2("PDF = ? AND Hash = ?", tSlug, tHash)
            if (tSameCount > 0) {
                set tOut.action = "duplicate"
                set tOut."existing_slug" = tSlug
                set tOut.rows = tSlugRows
            } else {
                set tOut.action = "replace"
                set tOut.rows = tSlugRows
            }
        }
    } else {
        // Slug mode: duplicate if slug has rows
        set tSlugRows = ..CountWhere("PDF = ?", tSlug)
        if (tSlugRows > 0) {
            set tOut.action = "duplicate"
            set tOut."existing_slug" = tSlug
            set tOut.rows = tSlugRows
        } else {
            set tOut.action = "new"
        }
    }

    set %response.ContentType = "application/json"
    write tOut.%ToJSON()
    quit $$$OK
}

/// GET /dedup -> {"mode":"Slug|Content"}
ClassMethod DedupGet() As %Status
{
    set tOut = {}
    set tOut.mode = ..DedupMode()
    set %response.ContentType = "application/json"
    write tOut.%ToJSON()
    quit $$$OK
}

/// POST /dedup {"mode":"Slug|Content"} -> persists the policy, echoes it back.
ClassMethod DedupSet() As %Status
{
    try {
        set tBody = {}.%FromJSON(%request.Content)
        set tMode = $SELECT(tBody.mode = "Content": "Content", 1: "Slug")
        set ^RAG2026.Config("DedupMode") = tMode
        set tOut = {}
        set tOut.mode = tMode
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
