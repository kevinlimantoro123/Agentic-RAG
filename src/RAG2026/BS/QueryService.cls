Include Ensemble

/// Adapterless business service for the query path. Invoked programmatically by
/// RAG2026.REST.Dispatch via Ens.Director.CreateBusinessService("Query Service").
/// Forwards the request synchronously to the agent process.
Class RAG2026.BS.QueryService Extends Ens.BusinessService
{

Parameter SETTINGS = "TargetConfigName:Basic:selector?context={Ens.ContextSearch/ProductionItems?targets=1&productionName=@productionId}";

/// Production item to forward to.
Property TargetConfigName As %String [ InitialExpression = "Agent Process" ];

Method OnProcessInput(pInput As RAG2026.Msg.QueryRequest, Output pOutput As RAG2026.Msg.QueryResponse) As %Status
{
    quit ..SendRequestSync(..TargetConfigName, pInput, .pOutput)
}

}
