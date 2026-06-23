Include Ensemble

/// One-shot environment setup for the RAG2026 namespace. Run after the classes are
/// loaded and interoperability is enabled. Idempotent.
///
///   do ##class(RAG2026.Setup).Init("sk-...openai...","tvly-...tavily...")
///
/// Creates: the llm_ssl TLS config (in %SYS), the OpenAIKey + TavilyKey interop
/// credentials, and the 'openai-embedding-config' %Embedding.Config (OpenAI,
/// text-embedding-3-small, 1536-dim).
Class RAG2026.Setup Extends %RegisteredObject
{

ClassMethod Init(pOpenAIKey As %String, pTavilyKey As %String = "", pSSLConfig As %String = "llm_ssl", pEmbeddingConfig As %String = "openai-embedding-config") As %Status
{
    set tSC = $$$OK
    try {
        if (pOpenAIKey = "") { throw ##class(%Exception.General).%New("Init", 1, , "OpenAI API key is required") }

        // 1) TLS config (system-wide; must be created in %SYS)
        $$$ThrowOnError(..EnsureSSL(pSSLConfig))

        // 2) Interoperability credentials
        $$$ThrowOnError(##class(Ens.Config.Credentials).SetCredential("OpenAIKey", "", pOpenAIKey))
        if (pTavilyKey '= "") {
            $$$ThrowOnError(##class(Ens.Config.Credentials).SetCredential("TavilyKey", "", pTavilyKey))
        }

        // 3) Embedding config used by Embedding.Clinical
        $$$ThrowOnError(..RegisterEmbeddingConfig(pOpenAIKey, pSSLConfig, pEmbeddingConfig))

        write "RAG2026 setup complete.",!
    } catch ex {
        set tSC = ex.AsStatus()
        write "Setup FAILED: ",$system.Status.GetErrorText(tSC),!
    }
    quit tSC
}

/// Create the SSL/TLS client config if it does not already exist (runs in %SYS).
ClassMethod EnsureSSL(pName As %String) As %Status
{
    set tSC = $$$OK
    new $namespace
    set $namespace = "%SYS"
    if '##class(Security.SSLConfigs).Exists(pName) {
        set tSC = ##class(Security.SSLConfigs).Create(pName)
    }
    quit tSC
}

/// Register (replace) the %Embedding.Config row that drives the EMBEDDING() columns.
ClassMethod RegisterEmbeddingConfig(pOpenAIKey As %String, pSSLConfig As %String, pConfigName As %String) As %Status [ Language = python ]
{
    import iris, json
    cfg = {"apiKey": pOpenAIKey, "sslConfig": pSSLConfig, "modelName": "text-embedding-3-small"}
    iris.sql.exec("DELETE FROM %Embedding.Config WHERE Name = ?", pConfigName)
    iris.sql.exec(
        "INSERT INTO %Embedding.Config "
        "(Name, Configuration, EmbeddingClass, VectorLength, Description) "
        "VALUES (?, ?, '%Embedding.OpenAI', 1536, 'OpenAI text-embedding-3-small')",
        pConfigName, json.dumps(cfg),
    )
    return 1
}

}
