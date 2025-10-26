import sys
import os
import time
import threading
# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sqlite3
import pandas as pd
from pathlib import Path
from pydantic import BaseModel
import duckdb

from fastapi import FastAPI, UploadFile,File, Form, HTTPException, Depends
from fastapi import BackgroundTasks
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from langchain_community.embeddings.openai import OpenAIEmbeddings
from dotenv import load_dotenv
from langchain_core.documents import Document

from rag_utils.rag_module import run_indexer,vectorstore,get_rag_chain
from rag_utils.query_classifier import detect_query_type_llm
from rag_utils.csv_query import ask_csv
from rag_utils.rag_chain import ask_rag

app = FastAPI()
security = HTTPBasic()
load_dotenv()

# -------------------------
# === DUCKDB SETUP ===
# -------------------------
# Set path to DuckDB database file using absolute path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DUCKDB_DIR = Path(BASE_DIR) / "static" / "data"
DUCKDB_DIR.mkdir(parents=True, exist_ok=True)  # ensure directory exists

DUCKDB_PATH = DUCKDB_DIR / "structured_queries.duckdb"

def initialize_duckdb():
    """Initialize DuckDB with required tables"""
    with duckdb.connect(str(DUCKDB_PATH)) as duck_conn:
        duck_conn.execute("""
            CREATE TABLE IF NOT EXISTS tables_metadata (
                table_name TEXT,
                role TEXT
            )
        """)

# Initialize DuckDB on startup
initialize_duckdb()


# -------------------------
# === SQLITE DATABASE SETUP ===
# -------------------------

conn = sqlite3.connect("roles_docs.db", check_same_thread=False)
c = conn.cursor()
c.executescript("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    role TEXT,
    filepath TEXT NOT NULL,
    headers_str TEXT,
    embedded INTEGER DEFAULT 0
);

-- Add index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
""")
conn.commit()

def create_default_user():
    conn_local = sqlite3.connect("roles_docs.db")
    c_local = conn_local.cursor()
    import hashlib

    # Create all roles first
    roles = ["C-Level", "Engineering", "Marketing", "Finance", "HR", "General"]
    for role in roles:
        c_local.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (role,))

    # Create sample users with their credentials
    sample_users = [
         ("admin", "admin123", "C-Level")
      #  ("Tony", "password123", "Engineering"), 
       # ("Bruce", "securepass", "Marketing"),
        #("Sam", "financepass", "Finance"),
        #("Natasha", "hrpass123", "HR"),
        #("Nolan", "nolan123", "General")
    ]

    users_created = 0
    for username, password, role in sample_users:
        # Hash password using SHA-256
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        # Use INSERT OR IGNORE to skip existing users silently
        c_local.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
                      (username, hashed_pw, role))
        # Check if the insert actually added a row
        if c_local.rowcount > 0:
            users_created += 1
            print(f"✅ User '{username}' ({role}) created.")
    
    conn_local.commit()
    conn_local.close()
    
    if users_created > 0:
        print(f"🎉 Total {users_created} new users created successfully!")


# Create all sample users on startup
create_default_user()

# -------------------------
# === AUTHENTICATION ===
# -------------------------
AUTH_CACHE_TTL = int(os.getenv("AUTH_CACHE_TTL", "600"))  # seconds, default 10 minutes
_AUTH_CACHE: dict[str, dict] = {}
_AUTH_LOCK = threading.Lock()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    import hashlib
    username = credentials.username
    password = credentials.password

    # Compute hash for cache key matching
    hashed_input = hashlib.sha256(password.encode()).hexdigest()

    now = time.time()
    with _AUTH_LOCK:
        entry = _AUTH_CACHE.get(username)
        if entry and entry.get("password_hash") == hashed_input and entry.get("expiry", 0) > now:
            # Return cached role without DB hit
            return {"username": username, "role": entry["role"]}

    # Fallback: verify against DB
    c.execute("SELECT password, role FROM users WHERE username = ?", (username,))
    row = c.fetchone()

    if not row or row[0] != hashed_input:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    role = row[1]

    # Update cache
    with _AUTH_LOCK:
        _AUTH_CACHE[username] = {
            "password_hash": hashed_input,
            "role": role,
            "expiry": now + AUTH_CACHE_TTL,
        }

    return {"username": username, "role": role}


def invalidate_auth_cache(username: str | None = None):
    """Invalidate entries in the in-memory auth cache.
    If username is None, clear the entire cache. Otherwise remove only that user.
    This should be called after create/delete user or role changes.
    """
    with _AUTH_LOCK:
        if username is None:
            _AUTH_CACHE.clear()
        else:
            _AUTH_CACHE.pop(username, None)

# === MODELS ===
class ChatMessage(BaseModel):
    role: str
    content: str
    
    class Config:
        extra = "ignore"  # Ignore extra fields like 'mode', 'sql' from UI

class ChatRequest(BaseModel):
    question: str
    # 'brief' (default) or 'extended' to control verbosity of RAG answers
    detail: str = "brief"
    # Optional conversation history for context-aware responses
    history: list[dict] = []  # Accept dicts instead of strict ChatMessage to be flexible

# -------------------------
# === ROUTES ===
# -------------------------

# Cache for roles list (updated when roles are created/deleted)
_ROLES_CACHE: list[str] = []
_ROLES_CACHE_LOCK = threading.Lock()

def get_cached_roles() -> list[str]:
    """Get roles from cache or fetch from DB if cache is empty"""
    with _ROLES_CACHE_LOCK:
        if not _ROLES_CACHE:
            c.execute("SELECT role_name FROM roles")
            _ROLES_CACHE.extend([r[0] for r in c.fetchall()])
        return _ROLES_CACHE.copy()

def invalidate_roles_cache():
    """Clear roles cache when roles are modified"""
    with _ROLES_CACHE_LOCK:
        _ROLES_CACHE.clear()

@app.get("/login")
def login(user=Depends(authenticate)):
    """Fast login endpoint that returns user info + roles in one call"""
    return {
        "message": f"Welcome {user['username']}!",
        "username": user['username'],
        "role": user["role"],
        "roles": get_cached_roles()  # Include roles to avoid second request
    }

@app.get("/roles")
def get_roles(user=Depends(authenticate)):
    """Get available roles (cached for performance)"""
    return {"roles": get_cached_roles()}
    return {"roles": roles}

@app.post("/create-user")
def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user=Depends(authenticate)
):
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can create users.")

    c.execute("SELECT 1 FROM roles WHERE role_name = ?", (role,))
    if not c.fetchone():
        raise HTTPException(status_code=400, detail="Invalid role")

    import hashlib
    hashed = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed, role))
        conn.commit()
        # Ensure in-memory auth cache reflects new user immediately
        invalidate_auth_cache(username=None)  # clear cache to be safe
        return {"message": f"User '{username}' added with role '{role}'"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")

@app.post("/create-role")
def create_role(role_name: str = Form(...), user=Depends(authenticate)):
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can create roles.")

    try:
        c.execute("INSERT INTO roles (role_name) VALUES (?)", (role_name,))
        conn.commit()
        # Invalidate caches when role list changes
        invalidate_auth_cache(username=None)
        invalidate_roles_cache()
        return {"message": f"Role '{role_name}' created"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Role already exists")


@app.post("/delete-user")
def delete_user(username: str = Form(...), user=Depends(authenticate)):
    """Delete a user from the SQLite users table. Only C-Level can perform this."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can delete users.")

    # Ensure user exists
    c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    if not c.fetchone():
        raise HTTPException(status_code=400, detail=f"User '{username}' not found")

    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    # Remove this user from auth cache if present
    invalidate_auth_cache(username=username)
    return {"message": f"User '{username}' deleted"}


@app.post("/delete-role")
def delete_role(role_name: str = Form(...), user=Depends(authenticate)):
    """Delete a role from the roles table. Reassigns users and documents to 'General'. Only C-Level can perform this."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can delete roles.")

    if role_name == "C-Level":
        raise HTTPException(status_code=400, detail="Cannot delete the 'C-Level' role")

    # Check role exists
    c.execute("SELECT 1 FROM roles WHERE role_name = ?", (role_name,))
    if not c.fetchone():
        raise HTTPException(status_code=400, detail=f"Role '{role_name}' not found")

    # Ensure 'General' role exists so we can reassign safely
    c.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", ("General",))

    # Reassign users who had this role to 'General'
    c.execute("UPDATE users SET role = ? WHERE role = ?", ("General", role_name))

    # Reassign documents that belonged to this role to 'General'
    c.execute("UPDATE documents SET role = ? WHERE role = ?", ("General", role_name))

    # Also update DuckDB tables_metadata if present
    try:
        with duckdb.connect(str(DUCKDB_PATH)) as duck_conn:
            duck_conn.execute(
                "UPDATE tables_metadata SET role = 'general' WHERE role = ?",
                (role_name,)
            )
    except Exception:
        # Non-fatal if DuckDB is missing or update fails - main DB changes are still applied
        pass

    # Remove the role
    c.execute("DELETE FROM roles WHERE role_name = ?", (role_name,))
    conn.commit()

    # Invalidate caches because role list and user roles changed
    invalidate_auth_cache(username=None)
    invalidate_roles_cache()

    return {"message": f"Role '{role_name}' deleted; affected users/documents reassigned to 'General'"}



UPLOAD_DIR = "static/uploads"

@app.post("/upload-docs")
async def upload_docs(file: UploadFile = File(...), role: str = Form(...)):
    try:
        filename = file.filename
        extension = Path(filename).suffix.lower()

        # Prepare storage
        role_dir = os.path.join(UPLOAD_DIR, role)
        os.makedirs(role_dir, exist_ok=True)
        filepath = os.path.join(role_dir, filename)

        # Read content + save file
        data = await file.read()  # Read once

        with open(filepath, "wb") as f:
            f.write(data)  # Save file for future indexing

        # Convert to string content for validation (optional)
        if extension == ".csv":
            from io import BytesIO
            df = pd.read_csv(BytesIO(data))
            content = df.to_string(index=False)

             # Load for DuckDB
            df1 = pd.read_csv(filepath)
            table_name = Path(filepath).stem.replace("-", "_")

            # Save metadata including headers
            headers = df1.columns.tolist()
            headers_str = ",".join(headers)

            # Use connection management for DuckDB operations
            with duckdb.connect(str(DUCKDB_PATH)) as duck_conn:
                duck_conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df1")

                # ✅ Remove any existing metadata for this table to avoid duplicates
                duck_conn.execute(
                    "DELETE FROM tables_metadata WHERE table_name = ?",
                    (table_name,)
                )
                
                # ✅ Save metadata to DuckDB tables_metadata (always lowercase role)
                duck_conn.execute(
                    "INSERT INTO tables_metadata (table_name, role) VALUES (?, ?)",
                    (table_name, role.lower())
                )

        elif extension == ".md":
            content = data.decode("utf-8")
            headers_str = None  # explicitly set to None
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        # Save metadata to DB using global connection to avoid locking
        c.execute("INSERT INTO documents (filename, role, filepath,headers_str,embedded) VALUES (?, ?, ?,?,?)",
                  (filename, role, filepath, headers_str,0))
        #doc_id = c.lastrowid  # ✅ Get inserted doc ID
        conn.commit()
        
        run_indexer()
        print("Files indexed successfully")
        return JSONResponse(content={"message": f"{filename} uploaded successfully for role '{role}'."})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    
   
"""
@app.post("/chat")
async def chat(req: ChatRequest, user=Depends(authenticate)):
    role = user["role"]
    username = user["username"]
    question = req.question

    # 1. Detect mode: SQL or RAG
    mode = detect_query_type_llm(question)  # Re-enabled with 30s timeout
    print(f"Detected mode: {mode}")

    
    # 2. Route to appropriate handler
    if mode == "SQL":
        result = await ask_csv(question, role, username, return_sql=True)
        #result = await ask_csv(question) 
    else:
    
        result = await ask_rag(question, role)  # pass role to enforce role-based doc access

    return {
        "user": username,
        "role": role,
        "mode": mode,
        "answer": result["answer"],
        **({"sql": result["sql"]} if "sql" in result else {})
    }
"""
@app.post("/chat")
async def chat(req: ChatRequest, user=Depends(authenticate)):
    role = user["role"]
    username = user["username"]
    question = req.question
    history = req.history

    # 1. Detect mode: SQL or RAG
    mode = detect_query_type_llm(question)
    # Heuristic: counting questions should go to SQL for completeness
    ql = question.lower()
    if any(kw in ql for kw in ["how many", "count "]):
        mode = "SQL"
    print(f"Detected mode: {mode}")

    result = {}
    fallback_used = False

    # 2. Pre-check: If SQL mode but no tables available, skip SQL attempt
    if mode == "SQL":
        from rag_utils.csv_query import get_allowed_tables_for_role
        allowed_tables = get_allowed_tables_for_role(role)
        
        if not allowed_tables:
            print(f"[SQL Pre-check] No tables available for role '{role}'. Skipping SQL, using RAG.")
            mode = "RAG (no CSV tables available)"
            result = await ask_rag(question, role, detail=req.detail, history=history)
        else:
            print(f"[SQL Pre-check] {len(allowed_tables)} table(s) available: {allowed_tables}")
            try:
                result = await ask_csv(question, role, username, return_sql=True, history=history)

                if result.get("error"):
                    error_msg = result.get("answer", "Unknown error")
                    print(f"[SQL Error] {error_msg}")
                    raise ValueError(f"SQL blocked or failed: {error_msg}")
                
                if not result.get("answer", "").strip():
                    print(f"[SQL Warning] Empty answer returned")
                    raise ValueError("SQL returned empty result")

            except Exception as e:
                print(f"[SQL Fallback Triggered] Error: {e}")
                # Use the requested verbosity when falling back to RAG
                result = await ask_rag(question, role, detail=req.detail, history=history)
                fallback_used = True
                mode = "SQL → RAG fallback"

    else:
        # Respect verbosity preference for RAG answers
        result = await ask_rag(question, role, detail=req.detail, history=history)

    return {
        "user": username,
        "role": role,
        "mode": mode,
        "fallback": fallback_used,
        "answer": result["answer"],
        **({"sql": result["sql"]} if "sql" in result else {})
    }


@app.get("/debug/docs")
def list_documents(user=Depends(authenticate)):
    """Return list of uploaded documents from SQLite. C-Level only."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can access debug endpoints")
    c.execute("SELECT id, filename, role, filepath, headers_str, embedded FROM documents")
    rows = c.fetchall()
    docs = []
    for r in rows:
        docs.append({
            "id": r[0],
            "filename": r[1],
            "role": r[2],
            "filepath": r[3],
            "headers": r[4],
            "embedded": bool(r[5])
        })
    return {"documents": docs}


@app.post("/debug/reindex")
def trigger_reindex(user=Depends(authenticate)):
    """Trigger the indexer to embed any unembedded documents. C-Level only."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can access debug endpoints")
    try:
        run_indexer()
        return {"message": "Reindex triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/vectorstore")
def vectorstore_info(user=Depends(authenticate)):
    """Return basic vectorstore stats: number of documents/chunks. C-Level only."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can access debug endpoints")
    try:
        vs = vectorstore.get()
        docs = vs.get("documents", [])
        return {"documents_count": len(docs), "collections": list(vs.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/users")
def list_users(user=Depends(authenticate)):
    """Return list of users and their roles. C-Level only."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can access debug endpoints")
    c.execute("SELECT id, username, role FROM users")
    rows = c.fetchall()
    users = [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]
    return {"users": users}


@app.get("/download-doc/{doc_id}")
def download_document(doc_id: int, user=Depends(authenticate)):
    """Stream a document file by document id. C-Level only."""
    if user["role"] != "C-Level":
        raise HTTPException(status_code=403, detail="Only C-Level can download documents")
    c.execute("SELECT filepath, filename FROM documents WHERE id = ?", (doc_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    filepath, filename = row
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")
    from fastapi.responses import FileResponse
    return FileResponse(path=filepath, filename=filename, media_type='application/octet-stream')
