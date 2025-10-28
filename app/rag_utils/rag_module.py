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
    # Optimized chunk size for faster processing and retrieval
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,      # Reduced from 1000 for faster retrieval
        chunk_overlap=150    # Reduced from 200 for less redundancy
    )
    splits = text_splitter.split_documents(docs)
    vectorstore.add_documents(splits)
    
    print("Documents embedded and saved to vectorstore.")
    print("Total documents:", len(vectorstore.get()["documents"]))




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
    #"Answer thoroughly using only the context below. Provide details, examples or steps if applicable. If the information is not present in the context, reply exactly: 'I couldn't find an answer in the documents.' Do NOT invent or hallucinate any facts. Cite the source filename for each substantive claim. Maximum 400 words.\n"

    "{context}"
)

system_prompt_extended = (
    "Answer thoroughly using only the context below. Provide details, examples or steps if applicable. If the information is not present in the context, reply exactly: 'I couldn't find an answer in the documents.' Do NOT invent or hallucinate any facts. Cite the source filename for each substantive claim. Maximum 400 words.\n"
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
    # Tighter generation settings to speed up RAG responses without hurting quality
    temperature=0.0,     # Deterministic and concise
    timeout=120,         # Keep overall cap at 2 minutes
    num_predict=100,     # Lower max tokens to reduce generation time
    top_p=0.5,           # More focused sampling
    repeat_penalty=1.1   # Prevent repetition
)

question_answering_chain_brief = create_stuff_documents_chain(model, chat_prompt_brief)
question_answering_chain_extended = create_stuff_documents_chain(model, chat_prompt_extended)

# ==============================
# Add a Reranker
# ==============================

# Cache for RAG chains to avoid recreation
_CHAIN_CACHE = {}

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
    """Get or create a cached RAG chain for the given role and detail level."""
    # Create cache key
    cache_key = f"{user_role.lower()}_{detail}_{bool(cohere_api_key)}"
    
    # Return cached chain if available
    if cache_key in _CHAIN_CACHE:
        print(f"[RAG Cache] Using cached chain for {cache_key}")
        return _CHAIN_CACHE[cache_key]
    
    print(f"[RAG Cache] Creating new chain for {cache_key}")
    user_role = user_role.lower()

    if user_role == "c-level":
        # C-level sees everything; use MMR for diverse, smaller context set
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": 3,            # reduce retrieved docs
                "lambda_mult": 0.8 # balance relevance/diversity
            }
        )

    elif user_role == "general":
        # General role sees only general documents
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": 2,
                "lambda_mult": 0.8,
                "filter": {"role": "general"}
            }
        )

    else:
        # For extended/strict answers, restrict retrieval to the user's role only
        if detail and str(detail).lower() == "extended":
            retriever = vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "k": 3,  # reduce retrieved docs further in extended to keep latency bounded
                    "lambda_mult": 0.8,
                    "filter": {"role": user_role}
                }
            )
        else:
            # All other roles see their docs + general for brief answers
            retriever = vectorstore.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "k": 2,
                    "lambda_mult": 0.8,
                    "filter": {
                        "role": {"$in": [user_role, "general"]}
                    }
                }
            )

    # wrap with reranker
    # Only use reranker when explicitly requested (passed from caller)
    if cohere_api_key:
        print("Using cohere reranker")
        retriever = wrap_with_reranker(retriever, cohere_api_key, top_n=3)

    # Choose QA chain based on requested detail
    if detail and detail.lower() == "extended":
        qa_chain = question_answering_chain_extended
    else:
        qa_chain = question_answering_chain_brief

    chain = create_retrieval_chain(retriever, qa_chain)
    
    # Cache the chain
    _CHAIN_CACHE[cache_key] = chain
    
    return chain
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

