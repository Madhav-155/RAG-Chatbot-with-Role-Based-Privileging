import re
import duckdb
import os, tabulate
import requests
import json
import sqlite3
import os
from pathlib import Path

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "roles_docs.db")

# DuckDB setup
DUCKDB_DIR = os.path.join(BASE_DIR, "static", "data")
os.makedirs(DUCKDB_DIR, exist_ok=True)  # Create directory if it doesn't exist
DUCKDB_FILE = os.path.join(DUCKDB_DIR, "structured_queries.duckdb")

def get_duck_connection():
    """Get a DuckDB connection with proper connection management"""
    return duckdb.connect(DUCKDB_FILE, read_only=False)

# Ollama setup
OLLAMA_URL = "http://localhost:11434/api/generate"

def get_allowed_tables_for_role(role: str) -> list[str]:
    with get_duck_connection() as duck_conn:
        if role.lower() == "c-level":
            query = "SELECT table_name FROM tables_metadata"
            return [row[0] for row in duck_conn.execute(query).fetchall()]
        elif role.lower() == "general":
            query = "SELECT table_name FROM tables_metadata WHERE role = 'general'"
            return [row[0] for row in duck_conn.execute(query).fetchall()]
        else:
            query = """
            SELECT table_name FROM tables_metadata
            WHERE role = ? OR role = 'general'
            """
            return [row[0] for row in duck_conn.execute(query, [role]).fetchall()]

def extract_tables_from_sql(sql: str) -> list[str]:
    # Extract tables used in FROM and JOIN clauses
    return re.findall(r'FROM\s+(\w+)|JOIN\s+(\w+)', sql, flags=re.IGNORECASE)

def flatten_matches(matches: list[tuple]) -> list[str]:
    return [item for tup in matches for item in tup if item]

FORBIDDEN = ["insert", "update", "delete", "drop", "alter", "create"]

def is_safe_query(sql: str) -> bool:
    lowered = sql.strip().lower().rstrip(";")
    return lowered.startswith("select") and all(word not in lowered for word in FORBIDDEN)

def translate_nl_to_sql(question: str, allowed_tables: list[str]) -> str:
    print("translate_nl_to_sql() called")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    print("Using DB path:", DB_PATH)
    cur = conn.cursor()

    # fetch headers from table
    cur.execute("""
        SELECT filename, headers_str FROM documents 
        WHERE embedded = 1 AND headers_str IS NOT NULL
    """)
    rows = cur.fetchall()
    print("Raw rows from DB:", rows)
    conn.close()

    schemas = []
    for filename, headers_str in rows:
        try:
            print("inside schemas")
            table_name = Path(filename).stem.replace("-", "_")
            print(table_name)
            cols = ", ".join(headers_str.split(","))
            print(cols)
            schemas.append(f"Table: {table_name}\nColumns: {cols}")
        except Exception as e:
            print(f"❌ Error while building schema for {filename}: {e}")

    print("Schemas:", schemas)

    schema_block = "\n\n".join(schemas)
    print("schema_block:\n", schema_block)

    # Prompt for LLM
    prompt = f"""
    You are an assistant that converts natural language questions into safe SQL SELECT queries.

    Use only the following schemas:
    {schema_block}

    Constraints:
    - Use only the tables listed above.
    - Use the exact column names as-is (including hyphens, underscores, casing).
    - Return only a SELECT query (no INSERT/UPDATE/DELETE).
    - If asked about 'employee name', consider alternatives like 'full-name', 'last-name'.
    - If asked about 'position', consider synonyms like 'role', 'designation'.
    - Do not mix aggregate functions (like COUNT(*)) with *. Use either a grouped summary or return them separately."
    Natural Language Question: "{question}"

    SQL:
    """

    try:
        ollama_payload = {
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        
        response = requests.post(OLLAMA_URL, json=ollama_payload)
        
        if response.status_code != 200:
            return f"Ollama LLM error: {response.text}"
        
        llm_answer = response.json()["response"]
        print("LLM call successful")
        print("Raw SQL from LLM:\n", llm_answer)
        
        return llm_answer

    except Exception as e:
        print("❌ LLM call failed:", e)
        return "Error generating SQL"

async def ask_csv(question: str, role: str, username: str, return_sql: bool = False) -> dict:
    allowed_tables = get_allowed_tables_for_role(role)

    try:
        sql = translate_nl_to_sql(question, allowed_tables)
        print(f"[SQL GENERATED]:\n{sql}")

        if not is_safe_query(sql):
            return {"answer": "Only SELECT queries are allowed.", "error": True}

        raw_matches = extract_tables_from_sql(sql)
        referenced_tables = flatten_matches(raw_matches)

        for table in referenced_tables:
            if table not in allowed_tables:
                return {"answer": f"Access denied to table: {table}", "error": True}

        with get_duck_connection() as duck_conn:
            result = duck_conn.execute(sql).fetchall()
            columns = [desc[0] for desc in duck_conn.description]
        
        output = [list(row) for row in result]

        markdown_table = tabulate.tabulate(output, headers=columns, tablefmt="github")
        response = {
            "answer": markdown_table if output else "Query executed, but no results found."
        }

        if return_sql:
            response["sql"] = sql

        return response

    except Exception as e:
        return {"answer": f"❌ Error: {str(e)}", "error": True}
