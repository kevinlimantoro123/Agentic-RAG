/// Agentic RAG production. IRIS is the orchestration layer: REST services -> business
/// processes -> business operations, with the vector store in Embedding.Clinical.
Class RAG2026.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="RAG2026.Production" TestingEnabled="true" LogGeneralTraceEvents="false">
  <Description>Agentic clinical RAG orchestrated by IRIS Interoperability (OpenAI + HNSW).</Description>
  <ActorPoolSize>2</ActorPoolSize>

  <Item Name="Query Service" ClassName="RAG2026.BS.QueryService" Category="Query" PoolSize="0" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="Agent Process" ClassName="RAG2026.BP.AgentProcess" Category="Query" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="MaxIterations">10</Setting>
    <Setting Target="Host" Name="DefaultTopK">5</Setting>
  </Item>
  <Item Name="LLM Operation" ClassName="RAG2026.BO.LLMOperation" Category="Query" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="Model">gpt-4o</Setting>
    <Setting Target="Host" Name="APIKeyCredentials">OpenAIKey</Setting>
  </Item>
  <Item Name="Retrieve Operation" ClassName="RAG2026.BO.RetrieveOperation" Category="Query" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="EmbeddingConfig">openai-embedding-config</Setting>
  </Item>
  <Item Name="Guideline Operation" ClassName="RAG2026.BO.GuidelineOperation" Category="Query" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="TavilyCredentials">TavilyKey</Setting>
  </Item>

  <Item Name="Ingest Service" ClassName="RAG2026.BS.IngestService" Category="Ingest" PoolSize="0" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="Ingest Process" ClassName="RAG2026.BP.IngestProcess" Category="Ingest" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="Prepare Operation" ClassName="RAG2026.BO.PrepareOperation" Category="Ingest" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="SidecarURL">http://127.0.0.1:8800/prepare</Setting>
    <Setting Target="Host" Name="WorkDir">/opt/app/data/</Setting>
    <Setting Target="Host" Name="RequestTimeout">600</Setting>
  </Item>
  <Item Name="Load Operation" ClassName="RAG2026.BO.LoadOperation" Category="Ingest" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
    <Setting Target="Host" Name="EmbeddingConfig">openai-embedding-config</Setting>
  </Item>

</Production>
}

}
