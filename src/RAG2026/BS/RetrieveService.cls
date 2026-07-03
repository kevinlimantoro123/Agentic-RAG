Include Ensemble

/// Adapterless business service for the standalone retrieval path. Invoked
/// programmatically by RAG2026.REST.Dispatch via
/// Ens.Director.CreateBusinessService("Retrieve Service"), so an out-of-IRIS
/// agent (the LangGraph agent) can reach the HNSW Retrieve Operation over HTTP
/// without going through the in-IRIS Agent Process. Mirrors RAG2026.BS.QueryService;
/// forwards the request synchronously to Retrieve Operation.
Class RAG2026.BS.RetrieveService Extends Ens.BusinessService
{

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

/// Production item to forward to.
Property TargetConfigName As %String [ InitialExpression = "Retrieve Operation" ];

Method OnProcessInput(pInput As RAG2026.Msg.RetrieveRequest, Output pOutput As RAG2026.Msg.RetrieveResponse) As %Status
{
    quit ..SendRequestSync(..TargetConfigName, pInput, .pOutput)
}

}
