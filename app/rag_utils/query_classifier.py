import requests
import os
from functools import lru_cache
import hashlib

# Ollama setup
OLLAMA_URL = "http://localhost:11434/api/generate"

# Fast keyword-based classification (no LLM needed)
SQL_KEYWORDS = [
    "how many", "count", "total", "sum", "average", "avg", "max", "min",
    "filter", "greater than", "less than", "equal to", "top ", "bottom ", 
    "group by", "employees in", "list all", "show all", "details of employee",
    "whose", "where", "with", "having", "highest", "lowest", "most", "least",
    "employee", "employees", "salary", "department", "rating", "hired", 
    "find", "get", "fetch", "retrieve"
]

RAG_KEYWORDS = [
    "summary", "summarize", "explain", "what is", "describe", "tell me about",
    "overview", "introduction", "define", "meaning of", "process", "steps",
    "highlights", "campaign", "report summary", "why", "how to", "strategy",
    "policy", "policies", "guidelines", "about", "understand"
]

def fast_classify(question: str) -> str | None:
    """Fast keyword-based classification. Returns None if uncertain."""
    q_lower = question.lower()
    # Normalize phrases that can confuse SQL detection (e.g., "employee handbook" is a doc, not a table)
    q_norm = q_lower.replace("employee handbook", "handbook")
    
    # Strong SQL indicators with explicit patterns
    sql_patterns = [
        "details of employee",
        "employees in",
        "employees whose",
        "employees with",
        "show me employee",
        "show employee",
        "list employee",
        "get employee",
        "find employee",
        "greater than",
        "less than",
        "equal to",
        "rating >",
        "rating <",
        "rating =",
        "performance rating",
        "salary",
        "who has",
        "which department",
        "hired in",
        "working in",
        "from department",
        "in department"
    ]
    
    # Strong RAG indicators
    rag_patterns = [
        "tell me about",
        "explain the",
        "describe the",
        "summary of",
        "summarize the",
        "highlights of",
        "overview of"
    ]
    
    # Check for strong RAG patterns first (to avoid SQL false positives)
    # But exclude if it contains SQL-related terms like "salary", "employee", etc.
    # Use normalized text so phrases like "employee handbook" don't count as SQL-y
    has_sql_terms = any(term in q_norm for term in ["salary", "employee", "rating", "department", "count", "total"])
    
    if not has_sql_terms:
        if any(pattern in q_lower for pattern in rag_patterns) or ("handbook" in q_lower):
            return "RAG"

    # Strong override: document-oriented nouns + explanation verbs => RAG
    doc_nouns = ["handbook", "report", "policy", "policies", "guidelines"]
    explain_verbs = ["summarize", "summary", "explain", "describe", "what is", "overview"]
    if any(n in q_lower for n in doc_nouns) and any(v in q_lower for v in explain_verbs):
        return "RAG"
    
    # Check for strong SQL patterns
    if any(pattern in q_lower for pattern in sql_patterns):
        return "SQL"
    
    # Check for strong SQL indicators
    sql_score = sum(1 for keyword in SQL_KEYWORDS if keyword in q_norm)
    rag_score = sum(1 for keyword in RAG_KEYWORDS if keyword in q_lower)
    
    # Definitive SQL patterns
    if sql_score >= 2:
        return "SQL"
    
    # Definitive RAG patterns
    if rag_score >= 2:
        return "RAG"
    
    # Single strong keyword checks
    if any(kw in q_lower for kw in ["how many", "count ", "total number", "average", "sum of"]):
        return "SQL"
    
    if any(kw in q_lower for kw in ["summary", "summarize", "explain what", "tell me about"]):
        return "RAG"
    
    # If mixed or unclear, return None to trigger LLM
    return None

@lru_cache(maxsize=100)
def _cached_llm_classify(question_hash: str, question: str) -> str:
    """Cached LLM classification to avoid repeated calls for same questions."""
    prompt = f"""
You are a classifier that decides if a user's question should be handled by structured SQL query logic or by unstructured document search (RAG).

If the question contains terms related to **structured data analysis** (e.g., "average", "sum", "total", "count", "how many", "filter", "greater than", "less than", "top 5", "group by", "details of employee" etc.), classify it as:

→ "SQL"

If the question is more about general understanding, summarization, definitions, or cannot be answered from structured tabular data, classify it as:
If question is about summary of a document, process etc classify it as
→ "RAG"

Respond with only one word: either **SQL** or **RAG**.

Here is the question:

"{question}"

Answer:
    """

    ollama_payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 10}  # Very short output needed
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=ollama_payload, timeout=15)  # Reduced timeout
        
        if response.status_code != 200:
            return "RAG"  # Default fallback
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        print("⚠️ Query classifier timeout/connection error - defaulting to RAG")
        return "RAG"  # Default fallback
    
    result = response.json()["response"].strip().upper()
    
    # Extract SQL or RAG from the response
    if "SQL" in result:
        return "SQL"
    else:
        return "RAG"

def detect_query_type_llm(question: str) -> str:
    """Detect query type with fast keyword matching first, LLM fallback if needed."""
    # Try fast classification first
    fast_result = fast_classify(question)
    if fast_result:
        print(f"[Fast Classifier] {fast_result} (skipped LLM)")
        return fast_result
    
    # Fall back to LLM with caching
    question_hash = hashlib.md5(question.lower().encode()).hexdigest()
    result = _cached_llm_classify(question_hash, question)
    print(f"[LLM Classifier] {result}")
    return result
