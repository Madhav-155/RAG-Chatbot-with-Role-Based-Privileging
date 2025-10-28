from rag_utils.rag_module import get_rag_chain
from rag_utils.secret_key import cohere_api_key


async def ask_rag(question: str, role: str, detail: str = "brief", use_cohere: bool = False, history: list = None) -> dict:
    """Ask the RAG chain and return an answer. detail: 'brief' or 'extended'."""
    api_key = cohere_api_key if use_cohere else None

    # Simple in-memory cache to speed up repeated questions (10 min TTL)
    # Keyed by (role, detail, normalized_question)
    global _RAG_ANSWER_CACHE
    try:
        _RAG_ANSWER_CACHE
    except NameError:
        _RAG_ANSWER_CACHE = {}
    CACHE_TTL = 600.0

    def _now():
        import time as _t
        return _t.time()

    def _norm(q: str) -> str:
        return " ".join((q or "").strip().lower().split())

    cache_key = (role.lower(), (detail or "brief").lower(), _norm(question))
    entry = _RAG_ANSWER_CACHE.get(cache_key)
    if entry and entry.get("expiry", 0) > _now():
        # Return cached result immediately
        return entry["value"]

    # Format history for context
    history_context = ""
    if history:
        # Take last few exchanges for context (reduce tokens for faster responses)
        for msg in history[-4:]:
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

    # If nothing useful found for this role, try a single fallback to General handbook
    not_found_phrase = "i couldn't find an answer in the documents"
    need_general_fallback = (
        (not answer or not sources or (not_found_phrase in (answer or "").lower()))
        and role.lower() != "general"
    )

    if need_general_fallback:
        general_chain = get_rag_chain(user_role="General", cohere_api_key=api_key, detail=detail)
        g_result = general_chain.invoke({"input": enhanced_question})
        g_answer = g_result.get("answer")
        g_context_docs = g_result.get("context", [])
        g_sources = []
        for d in g_context_docs:
            md = getattr(d, "metadata", {}) or d.get("metadata", {})
            src = md.get("source") if isinstance(md, dict) else None
            if src and src not in g_sources:
                g_sources.append(src)

        # Use general fallback only if it produced something non-empty
        if g_answer and g_sources:
            answer = g_answer
            context_docs = g_context_docs
            sources = g_sources

    response = {"answer": answer, "context": context_docs, "sources": sources}

    # Store in cache
    _RAG_ANSWER_CACHE[cache_key] = {"value": response, "expiry": _now() + CACHE_TTL}

    return response