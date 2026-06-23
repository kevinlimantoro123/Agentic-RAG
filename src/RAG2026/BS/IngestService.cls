Include Ensemble

/// Adapterless business service for the ingestion path. Invoked programmatically by
/// RAG2026.REST.Dispatch via Ens.Director.CreateBusinessService("Ingest Service").
Class RAG2026.BS.IngestService Extends Ens.BusinessService
{

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

/// Production item to forward to.
Property TargetConfigName As %String [ InitialExpression = "Ingest Process" ];

Method OnProcessInput(pInput As RAG2026.Msg.IngestRequest, Output pOutput As RAG2026.Msg.IngestResponse) As %Status
{
    quit ..SendRequestSync(..TargetConfigName, pInput, .pOutput)
}

}
