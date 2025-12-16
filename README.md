# RAG Chatbot with Role-Based Privileging

A self-hosted Retrieval-Augmented Generation (RAG) chatbot with role-based access control (RBAC). The system routes natural-language queries either to structured SQL over CSV-backed tables (via DuckDB) or to unstructured document search (RAG) using a local Ollama LLM and a Chroma vector index.

This repository contains a FastAPI backend, a Streamlit UI, document indexing utilities, and a test harness for validating multi-role behaviour.

Contents
--------
- `app/` - FastAPI app, Streamlit UI, and RAG utilities
	- `app/main.py` - FastAPI server and routing
	- `app/ui.py` - Streamlit front-end
	- `app/rag_utils/` - CSV→SQL, RAG chain, classifier, indexer code
	- `app/rag_evaluator/` - evaluation helpers and scripts
- `static/uploads/` - uploaded documents (organized by role)
- `chroma_db/` - persistent Chroma vectorstore files (created at runtime)
- `queries_by_role.txt` - curated prompts per role (RAG + optional SQL)
- `comprehensive_test_suite.py` - automated tests for roles and queries
- `TEST_REPORT.md` - last test run summary

Prerequisites
-------------
- Python 3.10+ (3.11 recommended)
- Git (optional)
- Local Ollama instance running (model `llama3.1` expected)
- (Optional) Cohere API key if you want reranking via Cohere
- `pip` and a virtual environment

Install dependencies
--------------------
Run these commands in Windows PowerShell from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

If you prefer not to use a virtualenv, install into your global environment, but virtualenvs are recommended.

Configuration
-------------
- Ollama: Make sure Ollama is installed and running and accessible at `http://localhost:11434`.
- Environment keys: `app/rag_utils/secret_key.py` is used for storing API keys (Cohere, LangChain) — you can either edit that file or set corresponding environment variables as needed.

Run the services
----------------
1. Start the FastAPI backend (runs on port 8000):

```powershell
# from project root
cd app

python -m venv venv

venv\Scripts\activate 


```
2.Install the dependencies:
```
pip install -r ../requirements.txt
```
3. In a new terminal, start the LLaMA 3 model using Ollama:
   ```powershell
	ollama run llama3.1
	```
4. Keep this terminal open — it runs the local LLM engine. The first run will download the model (~3–4 GB).

Go back to the backend terminal and start the FastAPI server:
```
uvicorn main:app --reload
```

4. Start the Streamlit UI (opens in browser):
In another new terminal:
```powershell
streamlit run app/ui.py
```

5. Embed Documents (Run Once Before Use)
To embed documents into ChromaDB:
```
python embed_documents.py
```
6. (Optional) If you add documents via the upload UI they will be saved under `static/uploads/<Role>/` and automatically indexed. To reindex manually (C-Level only API):

```powershell
# Trigger via API (requires C-Level credentials)
# Use your client (curl, httpie) or the Debug endpoint exposed by FastAPI
# Example (PowerShell):
$pair = "admin:admin123"  # replace with real creds
curl -u $pair -X POST http://localhost:8000/debug/reindex
```

Indexing and vector store
------------------------
- Documents (.md or .csv) uploaded through the UI are persisted and indexed by the indexer in `app/rag_utils/rag_module.py`.
- CSV files are created as DuckDB tables (`static/data/structured_queries.duckdb`) and also saved as documents for RAG when appropriate.
- The Chroma vectorstore is persisted to `chroma_db/`.

How the system routes queries
----------------------------
- Query classification: `app/rag_utils/query_classifier.py` decides whether a user question should run as SQL (structured) or RAG (document search).
- SQL mode: `app/rag_utils/csv_query.py` translates natural language to SQL (using Ollama), validates the SQL, executes it against DuckDB, and returns tabular results.
- RAG mode: `app/rag_utils/rag_chain.py` and `app/rag_utils/rag_module.py` retrieve relevant docs from Chroma and call Ollama for a generated answer.
- RBAC: DuckDB `tables_metadata` determines which DuckDB tables a role may query. Documents are tagged by role in the SQLite `roles_docs.db` and the vector retriever filters by role.

Security and safety
-------------------
- Only `SELECT` queries are allowed — destructive SQL (INSERT/UPDATE/DELETE/DDL) are blocked by `csv_query.is_safe_query`.
- Uploaded CSVs are turned into DuckDB tables using `CREATE OR REPLACE TABLE` and metadata is recorded in `tables_metadata`.
- Only C-Level users can create/delete roles and users via API or the admin UI.

Optimizations and performance tips
---------------------------------
- RAG queries are inherently slower than direct SQL. This project includes:
	- reduced token generation settings for Ollama,
	- MMR-style retrieval with small `k`,
	- a short in-memory RAG response cache for repeated queries.
- To further optimize RAG latency without affecting correctness:
	- Reduce the retriever `k` (number of retrieved chunks) in `app/rag_utils/rag_module.py`.
	- Enable the brief `detail` mode in the UI to request shorter answers.
	- Add caching at the HTTP layer for frequent identical queries.

Adding role-scoped SQL views (optional)
--------------------------------------
If you want Finance/Marketing/Engineering users to run safe aggregated SQL (no PII), create aggregated views in DuckDB and register them in `tables_metadata`. Example (run inside a Python shell with DuckDB available):

```python
import duckdb
duckdb_conn = duckdb.connect('static/data/structured_queries.duckdb')
duckdb_conn.execute("CREATE OR REPLACE VIEW hr_finance_department_comp AS SELECT department, COUNT(*) AS headcount, AVG(salary) AS avg_salary, SUM(salary) AS total_salary, AVG(performance_rating) AS avg_rating FROM hr_data GROUP BY department")
duckdb_conn.execute("INSERT INTO tables_metadata (table_name, role) VALUES ('hr_finance_department_comp','finance')")
```

Testing
-------
- Use the provided `comprehensive_test_suite.py` to run multi-role tests. It requires the FastAPI server and Ollama to be running. Example:

```powershell
python comprehensive_test_suite.py
```

Troubleshooting
---------------
- Ollama connection errors: Ensure Ollama is running and reachable at `http://localhost:11434`. Check the Ollama service logs.
- Vectorstore empty: Run the indexer or upload documents via the UI and call `/debug/reindex`.
- SQL generation timed out: SQL generation uses an LLM call with a timeout; simplifying the NL query or increasing Ollama resources will help.
- Long RAG responses: Try `brief` mode or enable caching / reduce retriever `k`.

Project maintenance
-------------------
- To add a new role, login as C-Level and use the Admin tab in Streamlit or call `POST /create-role`.
- To add a user, use the Admin UI (C-Level) or `POST /create-user` (C-Level only).
- Uploaded documents are stored under `static/uploads/<Role>/` and records are kept in `roles_docs.db`.

License
-------
This project follows the LICENSE file in the repository.



