# ========== CONFIG ==========
from pathlib import Path
import os
import pandas as pd
from collections import defaultdict
from langchain.schema import Document
import sqlite3


from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

from rag_utils.secret_key import langchain_key,cohere_api_key



# Disable LangSmith for better performance
os.environ["LANGCHAIN_TRACING_V2"] = "false"
# os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
# os.environ["LANGCHAIN_PROJECT"] = "RAG" 
# os.environ["LANGCHAIN_API_KEY"] = langchain_key
os.environ["COHERE_API_KEY"] = cohere_api_key


# ==============================
# ====Split,load,embed==========
# ==============================

# Use Ollama embeddings with nomic-embed-text model
ollama_embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Chroma(
    collection_name="my_collection",
    persist_directory="chroma_db",
    embedding_function=ollama_embeddings
)


def embed_documents_to_vectorstore(docs):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    vectorstore.add_documents(splits)
    
    print("Documents embedded and saved to vectorstore.")
    print("Total documents:", len(vectorstore.get()["documents"]))
    #print("Chunks being added:")
    #for chunk in splits:
    #    print(f"---\n{chunk.page_content[:150]}...\nMetadata: {chunk.metadata}")




def load_file(filepath, role):
    ext = Path(filepath).suffix.lower()
    try:
        if ext == ".csv":
            df1 = pd.read_csv(filepath)
            documents = []
            for row in df1.to_dict(orient="records"):
                content = "\n".join(f"{k}: {v}" for k, v in row.items())
                documents.append(
                    Document(
                        page_content=content,
                        metadata={"role": role.lower(), "source": Path(filepath).name}
                    )
                )
            return documents  # Return a list of documents

        elif ext == ".md":
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return [
                Document(
                    page_content=content,
                    metadata={"role": role.lower(), "source": Path(filepath).name}
                )
            ]
        else:
            return None

    except Exception as e:
        print(f"Failed to process {filepath}: {e}")
        return None


def run_indexer():
    conn = sqlite3.connect("roles_docs.db")
    c = conn.cursor()
    c.execute("SELECT id, filepath, role FROM documents WHERE embedded = 0")
    
    all_docs = []

    for doc_id, path, role in c.fetchall():
        docs = load_file(path, role)
        if docs:
            if isinstance(docs, list):
                all_docs.extend(docs)
            else:
                all_docs.append(docs)

            # Mark this file as embedded
            c.execute("UPDATE documents SET embedded = 1 WHERE id = ?", (doc_id,))

    if all_docs:
        embed_documents_to_vectorstore(all_docs)
        conn.commit()

    conn.close()
    print(f"Indexed {len(all_docs)} document chunks.")


# ==============================
# ========== PROMPT TEMPLATE ==========
# ==============================
# Two prompt styles: brief and extended
system_prompt_brief = (
    "Answer briefly using only the context below. Maximum 100 words.\n"
    "{context}"
)

system_prompt_extended = (
    "Answer thoroughly using only the context below. Provide details, examples or steps if applicable. Maximum 400 words.\n"
    "{context}"
)

chat_prompt_brief = ChatPromptTemplate.from_messages([
    ("system", system_prompt_brief),
    ("human", "{input}"),
])

chat_prompt_extended = ChatPromptTemplate.from_messages([
    ("system", system_prompt_extended),
    ("human", "{input}"),
])

# ==============================
# ========== MODEL ==========
# ==============================
model = Ollama(
    model="llama3.1",  
    temperature=0.8,     # Higher for faster responses
    timeout=120,         # Extended timeout for complex queries
    num_predict=100,     # Smaller response limit
    top_p=0.9,          # Focus on top predictions
    repeat_penalty=1.1   # Prevent repetition
)

question_answering_chain_brief = create_stuff_documents_chain(model, chat_prompt_brief)
question_answering_chain_extended = create_stuff_documents_chain(model, chat_prompt_extended)

# ==============================
# Add a Reranker
# ==============================
def wrap_with_reranker(retriever, cohere_api_key, top_n=4):
    #print("[INFO] Using Cohere reranker.")
    reranker = CohereRerank(
        cohere_api_key=cohere_api_key, 
        top_n=top_n,
        model="rerank-english-v3.0"  # Add required model parameter
    )
    return ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=retriever
    )

def get_rag_chain(user_role: str, cohere_api_key: str = None, detail: str = "brief"):
    user_role = user_role.lower()

    if user_role == "c-level":
        # C-level sees everything
        retriever = vectorstore.as_retriever(search_kwargs={"k": 2})  # Reduced for speed

    elif user_role == "general":
        # General role sees only general documents
        retriever = vectorstore.as_retriever(search_kwargs={
            "k": 2,  # Reduced for speed
            "filter": {"role": "general"}
        })

    else:
        # All other roles see their docs + general
        retriever = vectorstore.as_retriever(search_kwargs={
            "k": 2,  # Reduced for speed
            "filter": {
                "role": {"$in": [user_role, "general"]}
            }
        })

    # wrap with reranker
    if cohere_api_key:
        print("Using cohere reranker")
        retriever = wrap_with_reranker(retriever, cohere_api_key)

    # Choose QA chain based on requested detail
    if detail and detail.lower() == "extended":
        qa_chain = question_answering_chain_extended
    else:
        qa_chain = question_answering_chain_brief

    return create_retrieval_chain(retriever, qa_chain)
    """
    from langchain_core.runnables import RunnableLambda, RunnableMap

    extract_input = RunnableLambda(lambda x: x["input"])

    return RunnableMap({
        "context": extract_input | retriever,
        "answer": extract_input | retriever | question_answering_chain
    })"""


"""
# ========== MAIN EXECUTION ==========
if __name__ == "__main__":
    run_indexer() 
"""
    # ========== EXAMPLE USAGE ==========
"""
    user_role = "hr" 
    rag_chain = get_rag_chain(user_role)

    
    query = "give me Campaign Highlights from marketing summary."
    response = rag_chain.invoke({"input": query})

    print((response["answer"]))
    for doc in response.get("context", []):
        print(f"Source: {doc.metadata['source']}, Role: {doc.metadata.get('role')}")

"""

