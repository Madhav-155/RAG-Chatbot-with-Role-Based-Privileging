import re
import duckdb
import os, tabulate
import requests
import json
import sqlite3
import os
from pathlib import Path
from functools import lru_cache
import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "roles_docs.db")

# DuckDB setup
DUCKDB_DIR = os.path.join(BASE_DIR, "static", "data")
os.makedirs(DUCKDB_DIR, exist_ok=True)  # Create directory if it doesn't exist
DUCKDB_FILE = os.path.join(DUCKDB_DIR, "structured_queries.duckdb")

# Cache for table schemas with timestamp
_SCHEMA_CACHE = {}
_SCHEMA_CACHE_TTL = 300  # 5 minutes cache

def get_duck_connection():
    """Get a DuckDB connection with proper connection management"""
    return duckdb.connect(DUCKDB_FILE, read_only=False)

# Ollama setup
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_HEALTH_URL = "http://localhost:11434/api/tags"

def check_ollama_health():
    """Quick health check for Ollama service"""
    try:
        response = requests.get(OLLAMA_HEALTH_URL, timeout=2)
        return response.status_code == 200
    except:
        return False

@lru_cache(maxsize=50)
def get_allowed_tables_for_role(role: str) -> list[str]:
    """Cached version of allowed tables lookup"""
    rl = role.lower()
    with get_duck_connection() as duck_conn:
        if rl == "c-level":
            query = "SELECT table_name FROM tables_metadata"
            return [row[0] for row in duck_conn.execute(query).fetchall()]
        elif rl == "general":
            query = "SELECT table_name FROM tables_metadata WHERE role = 'general'"
            return [row[0] for row in duck_conn.execute(query).fetchall()]
        else:
            query = """
            SELECT table_name FROM tables_metadata
            WHERE role = ? OR role = 'general'
            """
            return [row[0] for row in duck_conn.execute(query, [rl]).fetchall()]

def get_cached_schemas() -> list[tuple]:
    """Get table schemas from cache or database"""
    global _SCHEMA_CACHE
    now = time.time()
    
    # Check if cache is valid
    if _SCHEMA_CACHE and _SCHEMA_CACHE.get("timestamp", 0) + _SCHEMA_CACHE_TTL > now:
        print("[Schema Cache] Using cached schemas")
        return _SCHEMA_CACHE["data"]
    
    # Fetch from database
    print("[Schema Cache] Refreshing schemas from DB")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        SELECT filename, headers_str FROM documents 
        WHERE embedded = 1 AND headers_str IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()
    
    # Update cache
    _SCHEMA_CACHE = {
        "data": rows,
        "timestamp": now
    }
    
    return rows

def invalidate_schema_cache():
    """Invalidate schema cache when documents are uploaded"""
    global _SCHEMA_CACHE
    _SCHEMA_CACHE = {}

def extract_tables_from_sql(sql: str) -> list[str]:
    # Extract tables used in FROM and JOIN clauses
    matches = re.findall(r'FROM\s+(\w+)|JOIN\s+(\w+)', sql, flags=re.IGNORECASE)
    # Filter out common SQL keywords and placeholders that might be mistakenly extracted
    excluded_keywords = [
        'table', 'tables', 'table_name', 'tablename',  # Common placeholders
        'select', 'where', 'group', 'order', 'by', 'having', 'limit', 'offset',  # SQL keywords
        'database', 'schema'  # Other common terms
    ]
    filtered_matches = []
    for match_tuple in matches:
        for item in match_tuple:
            if item and item.lower() not in excluded_keywords:
                filtered_matches.append((item,))
    return filtered_matches

def flatten_matches(matches: list[tuple]) -> list[str]:
    return [item for tup in matches for item in tup if item]

FORBIDDEN = ["insert", "update", "delete", "drop", "alter", "create"]

def is_safe_query(sql: str) -> bool:
    lowered = sql.strip().lower().rstrip(";")
    return lowered.startswith("select") and all(word not in lowered for word in FORBIDDEN)

def translate_nl_to_sql(question: str, allowed_tables: list[str], history: list = None) -> str:
    print("translate_nl_to_sql() called")
    
    # Quick health check before making expensive LLM call
    if not check_ollama_health():
        print("⚠️ Ollama service not responding")
        return "Error: LLM service unavailable"
    
    # Use cached schemas
    rows = get_cached_schemas()
    print("Raw rows from cache/DB:", rows)

    schemas = []
    for filename, headers_str in rows:
        try:
            table_name = Path(filename).stem.replace("-", "_")
            
            # IMPORTANT: Only include tables that the user has access to
            if table_name not in allowed_tables:
                print(f"[Schema] Skipping {table_name} - not in allowed_tables")
                continue
            
            # If no headers or empty string, it's likely a markdown document
            # But for CSV files, we should still include them and fetch schema from DuckDB
            if not headers_str or headers_str.strip() == "":
                # Check if it's a CSV file
                if filename.endswith('.csv'):
                    print(f"[Schema] CSV file {filename} has no headers_str, fetching from DuckDB...")
                    try:
                        with get_duck_connection() as duck_conn:
                            # Get actual columns from DuckDB
                            desc_result = duck_conn.execute(f"DESCRIBE {table_name}").fetchall()
                            actual_cols = [row[0] for row in desc_result]
                            cols = ", ".join(actual_cols)
                            schemas.append(f"Table: {table_name}\nColumns: {cols}")
                            print(f"[Schema] Added {table_name} with columns from DuckDB")
                    except Exception as e:
                        print(f"[Schema] Could not fetch schema for {table_name}: {e}")
                else:
                    print(f"[Schema] Skipping {filename} - empty headers and not CSV")
                continue
                
            cols = ", ".join(headers_str.split(","))
            schemas.append(f"Table: {table_name}\nColumns: {cols}")
            print(f"[Schema] Added {table_name} with {len(headers_str.split(','))} columns")
        except Exception as e:
            print(f"❌ Error while building schema for {filename}: {e}")

    schema_block = "\n\n".join(schemas)
    
    # If no valid schemas found, return error
    if not schema_block:
        print("❌ No valid CSV tables available for this role")
        return "Error: No accessible data tables found"

    # Format conversation history for context (reduced from 4 to 2 messages for speed)
    history_context = ""
    if history and len(history) > 0:
        for msg in history[-2:]:  # Only last exchange
            role_label = "User" if msg.get("role") == "user" else "Assistant"
            history_context += f"{role_label}: {msg.get('content', '')}\n"
        history_context = f"\nContext:\n{history_context}\n"

    # Ultra-simplified prompt for faster processing
    # Extract just the table names for emphasis
    table_names = []
    for line in schema_block.split('\n'):
        if line.startswith('Table:'):
            table_name = line.replace('Table:', '').strip()
            table_names.append(table_name)
    
    table_names_str = ", ".join(table_names)
    
    prompt = f"""Generate a SQL SELECT query.

IMPORTANT - USE ONLY THESE TABLE NAMES: {table_names_str}

Available tables with columns:
{schema_block}

User question: {question}
{history_context}

RULES:
1. MUST use one of these exact table names: {table_names_str}
2. DO NOT use placeholders like "table_name", "employees", "users"
3. For TEXT columns: use LOWER(TRIM(column)) = 'value'
4. For NUMERIC columns: use direct comparison (>=, <=, BETWEEN)
5. Return ONLY the SQL query

Example:
Question: "Finance employees rating 4+"
Answer: SELECT * FROM hr_data WHERE LOWER(TRIM(department)) = 'finance' AND performance_rating >= 4

SQL:"""

    try:
        ollama_payload = {
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0, 
                "num_predict": 100,     # Increased to ensure full SQL is generated
                "num_ctx": 512,         
                "top_k": 5,             
                "top_p": 0.3,           
                "repeat_penalty": 1.0
            }
        }
        
        # Timeout set to 45 seconds
        response = requests.post(OLLAMA_URL, json=ollama_payload, timeout=45)
        
        if response.status_code != 200:
            print(f"❌ Ollama returned status {response.status_code}")
            return f"Ollama LLM error: {response.text}"
        
        llm_answer = response.json()["response"].strip()
        print("LLM call successful")
        print("Raw SQL from LLM:\n", llm_answer)
        
        # Clean up the response - extract just the SQL
        sql_query = llm_answer
        
        # Method 1: Extract from SQL code block
        if "```sql" in sql_query.lower():
            parts = sql_query.lower().split("```sql")
            if len(parts) > 1:
                sql_query = parts[1].split("```")[0].strip()
        # Method 2: Extract from generic code block
        elif "```" in sql_query:
            parts = sql_query.split("```")
            if len(parts) > 1:
                sql_query = parts[1].split("```")[0].strip()
        
        # Method 3: Find the SELECT statement
        if not sql_query.strip().upper().startswith("SELECT"):
            # Look for SELECT in the text
            lines = sql_query.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.upper().startswith("SELECT"):
                    sql_query = stripped
                    break
        
        # Remove any remaining markdown or explanatory text
        sql_query = sql_query.strip()
        
        # If still no valid SQL, return error
        if not sql_query or not sql_query.upper().startswith("SELECT"):
            print(f"❌ Could not extract valid SQL from response: {llm_answer}")
            return "Error: Failed to generate valid SQL query"
        
        # Validate: Check if SQL contains placeholder table names
        sql_lower = sql_query.lower()
        placeholder_patterns = ['table_name', 'tablename', 'your_table', 'table_here', '<table']
        for placeholder in placeholder_patterns:
            if placeholder in sql_lower:
                print(f"❌ SQL contains placeholder '{placeholder}' - regenerating with clearer prompt")
                return "Error: SQL generation used placeholder table name. Please try again."
        
        # Validate: Check if any of the allowed tables are actually used
        has_valid_table = any(table.lower() in sql_lower for table in allowed_tables)
        if not has_valid_table:
            print(f"❌ SQL doesn't use any allowed tables. Allowed: {allowed_tables}")
            print(f"   SQL generated: {sql_query}")
            return f"Error: Generated SQL must use one of these tables: {', '.join(allowed_tables)}"
        
        print(f"Extracted SQL: {sql_query}")
        return sql_query

    except requests.exceptions.Timeout:
        print("❌ LLM call timed out after 45 seconds")
        return "Error: SQL generation timed out. Please try a simpler query."
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama. Is it running?")
        return "Error: Cannot connect to LLM service"
    except Exception as e:
        print(f"❌ LLM call failed: {type(e).__name__}: {e}")
        return f"Error generating SQL: {str(e)}"

async def ask_csv(question: str, role: str, username: str, return_sql: bool = False, history: list = None) -> dict:
    allowed_tables = get_allowed_tables_for_role(role)
    
    # Early exit if no tables available
    if not allowed_tables:
        print(f"[CSV Query] No tables available for role '{role}'")
        return {"answer": "No CSV tables available for your role.", "error": True}

    try:
        sql = translate_nl_to_sql(question, allowed_tables, history=history)
        print(f"[SQL GENERATED]:\n{sql}")
        
        # Check if SQL generation failed
        if not sql or sql.startswith("Error") or sql.startswith("Ollama"):
            print(f"[CSV Query] SQL generation failed: {sql}")
            return {"answer": f"Failed to generate SQL query: {sql}", "error": True}

        if not is_safe_query(sql):
            print(f"[CSV Query] Unsafe query blocked")
            return {"answer": "Only SELECT queries are allowed.", "error": True}

        raw_matches = extract_tables_from_sql(sql)
        referenced_tables = flatten_matches(raw_matches)
        
        # Convert to lowercase for comparison (DuckDB table names are case-insensitive)
        referenced_tables_lower = [t.lower() for t in referenced_tables]
        allowed_tables_lower = [t.lower() for t in allowed_tables]
        
        print(f"[CSV Query] Extracted tables from SQL: {referenced_tables} -> {referenced_tables_lower}")
        print(f"[CSV Query] Allowed tables for role '{role}': {allowed_tables} -> {allowed_tables_lower}")

        for i, table in enumerate(referenced_tables):
            table_lower = referenced_tables_lower[i]
            if table_lower not in allowed_tables_lower:
                print(f"[CSV Query] Access denied to table '{table}' for role '{role}'")
                return {"answer": f"Access denied to table: {table}", "error": True}

        with get_duck_connection() as duck_conn:
            result = duck_conn.execute(sql).fetchall()
            columns = [desc[0] for desc in duck_conn.description]
        
        output = [list(row) for row in result]

        # Check for empty results and provide helpful message
        if not output:
            # Try to understand why it's empty
            hint = ""
            if ">" in sql or "<" in sql:
                # Check if the filter is too restrictive
                hint = "\n\n💡 Tip: The filter condition might be too restrictive. In this dataset, performance ratings range from 1-5. Try adjusting your criteria (e.g., 'rating equal to 5' for top performers)."
            
            response_text = f"Query executed successfully, but no results found.{hint}"
            markdown_table = response_text
        else:
            markdown_table = tabulate.tabulate(output, headers=columns, tablefmt="github")
        
        response = {
            "answer": markdown_table
        }

        if return_sql:
            response["sql"] = sql

        print(f"[CSV Query] Success - returned {len(output)} row(s)")
        return response

    except Exception as e:
        print(f"[CSV Query] Exception: {type(e).__name__}: {str(e)}")
        return {"answer": f"❌ Error: {str(e)}", "error": True}
