from rag_utils.rag_module import get_rag_chain
from rag_utils.secret_key import cohere_api_key


async def ask_rag(question: str, role: str, detail: str = "brief", use_cohere: bool = False, history: list = None) -> dict:
    """Ask the RAG chain and return an answer. detail: 'brief' or 'extended'."""
    api_key = cohere_api_key if use_cohere else None
    
    # Format history for context
    history_context = ""
    if history:
        # Take last few exchanges for context (already limited to 10 messages in UI)
        for msg in history[-10:]:
            role_label = "User" if msg.get("role") == "user" else "Assistant"
            history_context += f"{role_label}: {msg.get('content', '')}\n"
    
    # Prepend history to question if available
    enhanced_question = question
    if history_context:
        enhanced_question = f"Previous conversation:\n{history_context}\n\nCurrent question: {question}"
    
    # Pass detail through to the chain builder so prompts can adjust verbosity
    chain = get_rag_chain(user_role=role, cohere_api_key=api_key, detail=detail)

    # Invoke the chain and request both the answer and retrieved context
    result = chain.invoke({"input": enhanced_question})

    answer = result.get("answer")
    context_docs = result.get("context", [])

    # Extract source filenames from retrieved documents (if present)
    sources = []
    for d in context_docs:
        md = getattr(d, "metadata", {}) or d.get("metadata", {})
        src = md.get("source") if isinstance(md, dict) else None
        if src:
            if src not in sources:
                sources.append(src)

    return {"answer": answer, "context": context_docs, "sources": sources}