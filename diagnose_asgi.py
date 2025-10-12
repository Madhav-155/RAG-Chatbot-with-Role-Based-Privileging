#!/usr/bin/env python3
"""
ASGI Error Diagnostic Script - identifies common FastAPI/ASGI issues
"""

import sys
import os
sys.path.append('app')

def test_chat_endpoint():
    """Test the chat endpoint that might be causing ASGI errors"""
    print("🧪 Testing Chat Endpoint...")
    
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        
        # Test data
        test_data = {
            "question": "Hello, test question"
        }
        
        auth = HTTPBasicAuth("admin", "admin123")
        
        print("📤 Sending test request...")
        response = requests.post(
            "http://localhost:8000/chat",
            json=test_data,
            auth=auth,
            timeout=30
        )
        
        print(f"📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Chat endpoint working!")
            result = response.json()
            print(f"📊 Mode: {result.get('mode', 'N/A')}")
            print(f"📝 Answer: {result.get('answer', 'N/A')[:100]}...")
        else:
            print(f"❌ Chat endpoint error: {response.status_code}")
            print(f"📄 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chat endpoint test failed: {e}")
        return False
    
    return True

def test_ollama_connection():
    """Test Ollama connection which might cause async issues"""
    print("\n🦙 Testing Ollama Connection...")
    
    try:
        import requests
        
        # Test Ollama health
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        
        if response.status_code == 200:
            models = response.json().get("models", [])
            print("✅ Ollama is running")
            print(f"📊 Available models: {len(models)}")
            
            # Check for required models
            model_names = [m["name"] for m in models]
            required_models = ["llama3.1:latest", "nomic-embed-text:latest"]
            
            for model in required_models:
                if model in model_names:
                    print(f"✅ Model {model} available")
                else:
                    print(f"⚠️ Model {model} not found")
        else:
            print(f"❌ Ollama error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Ollama connection failed: {e}")
        return False
    
    return True

def test_async_functions():
    """Test async functions that might cause ASGI errors"""
    print("\n🔄 Testing Async Functions...")
    
    try:
        import asyncio
        from app.rag_utils.rag_chain import ask_rag
        from app.rag_utils.csv_query import ask_csv
        
        async def test_rag():
            print("📄 Testing RAG function...")
            result = await ask_rag("What are the company policies?", "General")
            print(f"✅ RAG test successful: {len(result.get('answer', ''))} chars")
            return True
            
        async def test_csv():
            print("📊 Testing CSV function...")  
            result = await ask_csv("Show employee data", "HR", "admin", return_sql=True)
            if "error" not in result:
                print("✅ CSV test successful")
                return True
            else:
                print(f"⚠️ CSV test returned error: {result.get('answer', '')}")
                return True  # This is expected if no CSV data exists
        
        # Run async tests
        asyncio.run(test_rag())
        asyncio.run(test_csv())
        
    except Exception as e:
        print(f"❌ Async function test failed: {e}")
        return False
    
    return True

def test_database_locks():
    """Test for database locking issues"""
    print("\n🔒 Testing Database Locks...")
    
    try:
        import sqlite3
        from app.rag_utils.csv_query import get_duck_connection
        
        # Test SQLite
        conn = sqlite3.connect("roles_docs.db", timeout=5)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        user_count = c.fetchone()[0]
        conn.close()
        print(f"✅ SQLite OK: {user_count} users")
        
        # Test DuckDB
        duck_conn = get_duck_connection()
        try:
            duck_conn.execute("SELECT 1").fetchone()
            print("✅ DuckDB OK")
        finally:
            duck_conn.close()
            
    except Exception as e:
        print(f"❌ Database lock test failed: {e}")
        return False
    
    return True

def main():
    print("🔍 ASGI Error Diagnostic Starting...")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Run all tests
    tests = [
        test_ollama_connection,
        test_database_locks,
        test_async_functions,
        test_chat_endpoint
    ]
    
    for test_func in tests:
        try:
            result = test_func()
            if not result:
                all_tests_passed = False
        except Exception as e:
            print(f"❌ Test {test_func.__name__} crashed: {e}")
            all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("✅ All tests passed! ASGI error might be intermittent.")
        print("\n💡 Common ASGI Error Causes:")
        print("   1. Timeout issues (increase timeout)")
        print("   2. Concurrent request handling")
        print("   3. Memory issues with large embeddings")
        print("   4. Network issues with Ollama")
    else:
        print("❌ Some tests failed - this might be causing ASGI errors")
    
    print("\n🔧 Recommended Actions:")
    print("   1. Restart Ollama: ollama serve")
    print("   2. Restart FastAPI server")
    print("   3. Check system resources (RAM/CPU)")
    print("   4. Monitor server logs during requests")

if __name__ == "__main__":
    main()