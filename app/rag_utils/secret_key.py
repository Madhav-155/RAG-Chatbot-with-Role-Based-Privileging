# Configuration file for API keys
# Since we're using Ollama (local), we only need these keys for optional services
import os

# LangChain API key for tracing (optional)
# Set this in your environment: set LANGCHAIN_API_KEY=your_key_here
langchain_key = os.getenv("LANGCHAIN_API_KEY", "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")

# Cohere API key for reranking (optional)  
# Set this in your environment: set COHERE_API_KEY=your_key_here
cohere_api_key = os.getenv("COHERE_API_KEY", "TIhSC5AsN0Zn1iYO3pyrJ50vpbAPDGLya5f3LctG")

# Note: OpenAI API key is no longer needed as we're using Ollama locally