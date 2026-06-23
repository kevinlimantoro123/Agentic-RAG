/// Request to RAG2026.BO.RetrieveOperation (HNSW vector search over Embedding.Clinical).
Class RAG2026.Msg.RetrieveRequest Extends Ens.Request
{

Property Query As %String(MAXLEN = "");

Property Pdf As %String(MAXLEN = 200);

Property Patient As %String(MAXLEN = 200);

Property VisitDate As %String(MAXLEN = 50);

Property TopK As %Integer [ InitialExpression = 5 ];

}
