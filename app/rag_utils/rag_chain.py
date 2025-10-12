from rag_utils.rag_module import get_rag_chain
from rag_utils.secret_key import cohere_api_key


async def ask_rag(question: str, role: str, detail: str = "brief", use_cohere: bool = False) -> dict:
    """Ask the RAG chain and return an answer. detail: 'brief' or 'extended'."""
    api_key = cohere_api_key if use_cohere else None
    # Pass detail through to the chain builder so prompts can adjust verbosity
    chain = get_rag_chain(user_role=role, cohere_api_key=api_key, detail=detail)
    result = chain.invoke({"input": question})
    # result typically contains {"answer": ..., "context": [...]}
    return {"answer": result.get("answer"), "context": result.get("context", [])}