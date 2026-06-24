Include Ensemble

/// Prepare business operation: persists the uploaded PDF into the shared WorkDir
/// and calls the OUT-OF-PROCESS extractor sidecar (FastAPI) to run the heavy
/// extract -> clean -> chunk pipeline. The sidecar isolates unstructured/torch/OCR
/// so a crash can never take down IRIS.
/// 
/// Sidecar contract:  POST {SidecarURL}  body {"slug","pdf_path","work_dir"}
///                    returns            {"chunks_path": "...", "stats": {...}}
Class RAG2026.BO.PrepareOperation Extends Ens.BusinessOperation
{

Parameter INVOCATION = "Queue";

Parameter SETTINGS = "SidecarURL:Sidecar,WorkDir:Sidecar,RequestTimeout:Sidecar";

/// Full URL of the sidecar prepare endpoint.
Property SidecarURL As %String(MAXLEN = 500) [ InitialExpression = "http://127.0.0.1:8800/prepare" ];

/// Shared directory (visible to both IRIS and the sidecar) for PDFs + chunks.json.
Property WorkDir As %String(MAXLEN = 500) [ InitialExpression = "/opt/app/data/" ];

/// HTTP timeout in seconds for the (potentially slow) extraction call.
Property RequestTimeout As %Integer [ InitialExpression = 6000 ];

XData MessageMap
{
<MapItems>
  <MapItem MessageType="RAG2026.Msg.PrepareRequest">
    <Method>OnPrepare</Method>
  </MapItem>
</MapItems>
}

Method OnPrepare(pRequest As RAG2026.Msg.PrepareRequest, Output pResponse As RAG2026.Msg.PrepareResponse) As %Status
{
    set tSC = $$$OK
    set pResponse = ##class(RAG2026.Msg.PrepareResponse).%New()
    try {
        do pResponse.%JSONImport(..Prepare(pRequest.Slug, pRequest.PdfBase64, ..WorkDir, ..SidecarURL, ..RequestTimeout))
    } catch ex {
        set tSC = ex.AsStatus()
    }
    quit tSC
}

Method Prepare(pSlug As %String, pPdfB64 As %String, pWorkDir As %String, pUrl As %String, pTimeout As %Integer) As %String [ Language = python ]
{
    import os, base64, json, requests

    slug_dir = os.path.join(pWorkDir, pSlug)
    os.makedirs(slug_dir, exist_ok=True)
    pdf_path = os.path.join(slug_dir, pSlug + ".pdf")

    if pPdfB64:
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(pPdfB64))

    payload = {"slug": pSlug, "pdf_path": pdf_path, "work_dir": pWorkDir}
    # Short connect timeout (fail fast if the sidecar is down) + long read
    # timeout so a huge PDF's extraction doesn't trip a ReadTimeout. A
    # RequestTimeout of 0 (or less) means "no read limit" -- wait indefinitely.
    read_timeout = int(pTimeout)
    timeout = (30, read_timeout if read_timeout > 0 else None)
    r = requests.post(pUrl, json=payload, timeout=timeout)
    # Surface the sidecar's actual error body instead of a bare HTTPError.
    if r.status_code >= 400:
        raise RuntimeError("Sidecar " + str(r.status_code) + " for slug '" + str(pSlug) + "': " + r.text[:2000])
    data = r.json()

    out = {
        "slug": pSlug,
        "chunksPath": data.get("chunks_path", ""),
        "stats": json.dumps(data.get("stats", {})),
    }
    return json.dumps(out)
}

}
