import requests
import os

# Ollama setup
OLLAMA_URL = "http://localhost:11434/api/generate"

def detect_query_type_llm(question: str) -> str:
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
        "options": {"temperature": 0.0}
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=ollama_payload, timeout=120)
        
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
