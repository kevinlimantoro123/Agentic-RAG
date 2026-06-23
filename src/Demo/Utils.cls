Class Demo.Utils Extends %RegisteredObject
{

ClassMethod GetEmbeddingPy(sentences) As %SYS.Python [ Language = python ]
{
    import json
  
    # import the package   
    import sentence_transformers
        
    # create the model and form the embeddings
    model = sentence_transformers.SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(sentences)

    # convert the embeddings to a string
    embeddings_list = [str(embedding.tolist()) for embedding in embeddings]
    # print(embeddings_list[0])
    return embeddings_list
}

ClassMethod GetChunks(pText As %SYS.Python, pChunkSize As %Integer, pChunkOverlap As %Integer) As %SYS.Python [ Language = python ]
{
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    text_splitter = RecursiveCharacterTextSplitter(
    chunk_size = pChunkSize,
    chunk_overlap  = pChunkOverlap
    )
    docs = text_splitter.split_text(pText)

    return docs
}

}
