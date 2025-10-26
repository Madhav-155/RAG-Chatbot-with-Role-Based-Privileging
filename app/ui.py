import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import base64
import pandas as pd
import io

API_URL = "http://localhost:8000"

st.set_page_config(page_title="FinSolve Data Assistant", page_icon="🤖",layout="wide")
# -------------------------
# BACKGROUND IMAGES
# -------------------------
def set_bg_from_local(image_path):
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode()

    css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

set_bg_from_local("static/images/background.jpg")

# Load external UI stylesheet
def load_ui_css():
    try:
        with open("assets/ui.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

load_ui_css()
# Two-column layout
left_col, right_col = st.columns([7,1])

with left_col:
    st.markdown("""
    <div class="header-card">
        <h2 class="header-title">Welcome to FinSight</h2>
        <p class="header-subtitle">Your Document Assistant to get insights about Finsolve Technologies.</p>
    </div>
    """, unsafe_allow_html=True)

# -------------------------
# SESSION INIT
# -------------------------
if "auth" not in st.session_state:
    st.session_state.auth = None
if "role" not in st.session_state:
    st.session_state.role = None
if "page" not in st.session_state:
    st.session_state.page = "login"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "current_user" not in st.session_state:
    st.session_state.current_user = None

# Load roles into session state if not present
def fetch_roles():
    try:
        role_res = requests.get(f"{API_URL}/roles", auth=HTTPBasicAuth(*st.session_state.auth))
        return role_res.json().get("roles", [])
    except:
        return []


# -------------------------
# LOGIN PAGE
# -------------------------

if st.session_state.page == "login":
    # Inject JS to auto-fill and auto-login if credentials are in localStorage
    st.markdown("""
    <script>
    window.addEventListener('DOMContentLoaded', function() {
        let u = localStorage.getItem('fs_username');
        let p = localStorage.getItem('fs_password');
        if (u && p) {
            // Fill the fields and trigger login
            let inputs = document.querySelectorAll('input');
            if (inputs.length >= 2) {
                inputs[0].value = u;
                inputs[1].value = p;
                // Simulate login button click
                let btns = document.querySelectorAll('button');
                for (let b of btns) {
                    if (b.innerText.toLowerCase().includes('login')) {
                        b.click();
                        break;
                    }
                }
            }
        }
    });
    </script>
    """, unsafe_allow_html=True)

    st.markdown("",unsafe_allow_html=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        with st.spinner("Authenticating..."):
            res = requests.get(f"{API_URL}/login", auth=HTTPBasicAuth(username, password), timeout=10)
        if res.status_code == 200:
            data = res.json()
            
            # Check if this is a different user - if so, clear chat history
            if st.session_state.current_user != username:
                st.session_state.chat_history = []
                st.session_state.current_user = username
            
            st.session_state.auth = (username, password)
            st.session_state.username = username
            st.session_state.password = password
            st.session_state.role = data["role"]
            # Get roles from login response (no second request needed!)
            st.session_state.roles = data.get("roles", [])
            
            # Save credentials to localStorage for auto-login
            st.markdown(f"""
            <script>
            localStorage.setItem('fs_username', '{username}');
            localStorage.setItem('fs_password', '{password}');
            </script>
            """, unsafe_allow_html=True)
            
            st.session_state.page = "main"  # Navigate to main app
            st.rerun()
        else:
            try:
                st.error(res.json().get("detail", "Login failed."))
            except:
                st.error("Server error. Please check FastAPI logs.")



# -------------------------
# MAIN APP AFTER LOGIN
# -------------------------
if st.session_state.page == "main":
    username = st.session_state.username
    role = st.session_state.role

    with right_col:
        st.markdown(f"**👤 User:** `{username}`  \n**🛡️ Role:** `{role}`")
        # --- Logout ---
        if st.button("🚪 Logout"):
            # Clear all session data on logout
            st.session_state.auth = None
            st.session_state.role = None
            st.session_state.page = "login"
            st.session_state.chat_history = []  # Clear chat history
            st.session_state.current_user = None  # Clear current user
            st.session_state.username = None
            st.session_state.password = None
            st.session_state.roles = []
            
            # Clear localStorage
            st.markdown("""
            <script>
            localStorage.removeItem('fs_username');
            localStorage.removeItem('fs_password');
            </script>
            """, unsafe_allow_html=True)
            
            st.rerun()
    
        # Role-specific section
        # Dynamic rendering
    with left_col:
        st.markdown("")
        if role == "C-Level":
            st.write("You have global access")
            tab1, tab2, tab3, tab4 = st.tabs(["💬 Chat", "🧾 Upload (C-Level)", "👤 Admin (C-Level)", "📋 Overview (C-Level)"])
        
        elif role == "General":
            st.write(f"You have access to documents and features related to the `{role}` role.")
            (tab1,) = st.tabs(["💬 Chat"])

        else:
            st.write(f"You have access to documents and features related to the `{role}` role.")
            st.markdown("You also have access to **General documents** (e.g.,regulations, company policies, holidays, announcements)")
            (tab1,) = st.tabs(["💬 Chat"])
    
 
    # --- Chat Tab ---
    with tab1:
        st.subheader("💬 Chat with Assistant")
        
        # Add clear chat button
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("🗑️ Clear Chat"):
                st.session_state.chat_history = []
                st.rerun()
        
        # Display chat history
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    # Show mode and SQL if available
                    #if "mode" in msg:
                    #    st.caption(f"🔍 Mode: {msg['mode']}")
                    #if "sql" in msg:
                    #    with st.expander("🔎 View SQL Query"):
                    #        st.code(msg["sql"], language="sql")
        
        # Chat input at bottom
        question = st.chat_input("Type your question here...")
        
        if question:
            # Add user message to history
            st.session_state.chat_history.append({"role": "user", "content": question})
            
            # Display user message immediately
            with st.chat_message("user"):
                st.markdown(question)
            
            # Get response from backend
            with st.spinner(" Thinking..."):
                try:
                    # Send last 4 exchanges for context (8 messages = 4 Q&A pairs) - reduced for speed
                    history_for_api = st.session_state.chat_history[-8:] if len(st.session_state.chat_history) > 1 else []
                    
                    res = requests.post(
                        f"{API_URL}/chat",
                        json={
                            "question": question,
                            "role": st.session_state.role,
                            "detail": "brief",
                            "history": history_for_api
                        },
                        auth=HTTPBasicAuth(*st.session_state.auth),
                        timeout=150  # Increased from 120s to 150s (2.5 minutes) to handle SQL generation timeout
                    )
                    
                    if res.status_code == 200:
                        response_data = res.json()
                        answer = response_data["answer"]
                        mode = response_data.get("mode", "Unknown")
                        sql = response_data.get("sql")
                        
                        # Add assistant message to history
                        assistant_msg = {
                            "role": "assistant",
                            "content": answer,
                            "mode": mode
                        }
                        if sql:
                            assistant_msg["sql"] = sql
                        
                        st.session_state.chat_history.append(assistant_msg)
                        
                        # Display assistant message
                        with st.chat_message("assistant"):
                            # Check if answer is a markdown table
                            if mode == "SQL" and "|" in answer and answer.count("\n") > 1:
                                # It's a table - convert to dataframe for better display
                                try:
                                    # Parse markdown table
                                    lines = [line.strip() for line in answer.strip().split("\n") if line.strip() and not line.strip().startswith("|--")]
                                    
                                    if len(lines) >= 2:
                                        # Extract headers
                                        headers = [h.strip() for h in lines[0].split("|") if h.strip()]
                                        
                                        # Extract data rows
                                        data_rows = []
                                        for line in lines[1:]:
                                            if line.startswith("|"):
                                                row = [cell.strip() for cell in line.split("|") if cell.strip()]
                                                if row and len(row) == len(headers):
                                                    data_rows.append(row)
                                        
                                        # Create and display dataframe
                                        if data_rows:
                                            df = pd.DataFrame(data_rows, columns=headers)
                                            st.dataframe(df, use_container_width=True)
                                        else:
                                            st.markdown(answer)
                                    else:
                                        st.markdown(answer)
                                except Exception as e:
                                    # Fallback to markdown if parsing fails
                                    st.markdown(answer)
                            else:
                                # Regular text or RAG response
                                st.markdown(answer)
                            
                            st.caption(f"🔍 Mode: {mode}")
                            if sql:
                                with st.expander("🔎 View SQL Query"):
                                    st.code(sql, language="sql")
                    else:
                        error_msg = "❌ Something went wrong while processing your question."
                        st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
                        with st.chat_message("assistant"):
                            st.error(error_msg)
                            
                except Exception as e:
                    error_msg = f"❌ Error: {str(e)}"
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
                    with st.chat_message("assistant"):
                        st.error(error_msg)
            
            st.rerun()
        
            

    # --- Upload Tab (C-Level) ---
    if st.session_state.role == "C-Level":
        with tab2:
            st.subheader("Upload Documents")
            role_res = requests.get(f"{API_URL}/roles", auth=HTTPBasicAuth(*st.session_state.auth))
            #roles = role_res.json().get("roles", [])
            # Show all unique roles (case-insensitive, no filtering)
            allowed_set = set()
            allowed_roles = []
            for r in st.session_state.roles:
                rl = str(r).strip()
                rl_lower = rl.lower()
                if rl_lower not in allowed_set:
                    allowed_roles.append(rl)
                    allowed_set.add(rl_lower)
            selected_role = st.selectbox("Select document access role", allowed_roles)
            doc_files = st.file_uploader(
                "Upload document(s) (.md or .csv)",
                type=["csv", "md"],
                accept_multiple_files=True,
            )

            if st.button("Upload Document(s)") and doc_files:
                successes = 0
                failures = 0
                for doc_file in doc_files:
                    with st.spinner(f"Uploading {doc_file.name}..."):
                        try:
                            res = requests.post(
                                f"{API_URL}/upload-docs",
                                files={"file": doc_file},
                                data={"role": selected_role},
                                auth=HTTPBasicAuth(*st.session_state.auth),
                                timeout=120,
                            )
                            if res.ok:
                                st.success(res.json().get("message", f"{doc_file.name} uploaded successfully."))
                                successes += 1
                            else:
                                try:
                                    detail = res.json().get("detail", "Upload failed")
                                except Exception:
                                    detail = "Upload failed"
                                st.error(f"{doc_file.name}: {detail}")
                                failures += 1
                        except Exception as e:
                            st.error(f"{doc_file.name}: {e}")
                            failures += 1

                if len(doc_files) > 1:
                    st.info(f"Completed uploads. Success: {successes}, Failed: {failures}.")

        # --- Admin Tab (C-Level) ---
        with tab3:
            st.subheader("Add User")
            new_user = st.text_input("New Username")
            new_pass = st.text_input("New Password", type="password")
            new_role = st.selectbox("Assign Role", allowed_roles)
            if st.button("Create User"):
                with st.spinner("Creating user, please wait..."):
                    res = requests.post(
                        f"{API_URL}/create-user",
                        data={"username": new_user, "password": new_pass, "role": new_role},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                if res.ok:
                    st.success(res.json()["message"])
                else:
                    st.error(res.json().get("detail", "Something went wrong."))

            st.subheader("Create New Role")
            new_role_input = st.text_input("New Role Name")
            if st.button("Add Role"):
                with st.spinner("Adding new role, please wait..."):
                    res = requests.post(
                        f"{API_URL}/create-role",
                        data={"role_name": new_role_input},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                if res.ok:
                    st.success(res.json()["message"])
                    with st.spinner("Refreshing roles..."):
                        st.session_state.roles = fetch_roles()  # Refresh role list
                    st.rerun()  # Rerun so dropdowns get updated
                else:
                    st.error(res.json().get("detail", "Something went wrong."))

            st.markdown("---")
            st.subheader("Delete User")
            del_user = st.text_input("Username to delete")
            if st.button("Delete User") and del_user:
                with st.spinner("Deleting user, please wait..."):
                    res = requests.post(
                        f"{API_URL}/delete-user",
                        data={"username": del_user},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                if res.ok:
                    st.success(res.json().get("message", "User deleted"))
                else:
                    try:
                        st.error(res.json().get("detail", "Something went wrong."))
                    except:
                        st.error("Something went wrong.")

            st.subheader("Delete Role")
            # Filter out C-Level from deletion options (cannot delete C-Level)
            deletable_roles = [role for role in allowed_roles if role != "C-Level"]
            
            if deletable_roles:
                del_role = st.selectbox("Select role to delete", deletable_roles, key="delete_role_select")
                if st.button("Delete Role"):
                    with st.spinner("Deleting role, please wait..."):
                        res = requests.post(
                            f"{API_URL}/delete-role",
                            data={"role_name": del_role},
                            auth=HTTPBasicAuth(*st.session_state.auth)
                        )
                    if res.ok:
                        st.success(res.json().get("message", "Role deleted"))
                        with st.spinner("Refreshing roles..."):
                            st.session_state.roles = fetch_roles()
                        st.rerun()
                    else:
                        try:
                            st.error(res.json().get("detail", "Something went wrong."))
                        except:
                            st.error("Something went wrong.")
            else:
                st.info("No roles available for deletion (C-Level cannot be deleted)")

        # --- Overview Tab (C-Level) ---
        with tab4:
            st.subheader("C-Level Overview")
            st.markdown("This page lists users, roles, and uploaded documents. Only C-Level can access these controls.")

            # Ensure roles are available for filtering (prefer session cache)
            roles = st.session_state.get("roles") or []
            if not roles:
                try:
                    rr = requests.get(f"{API_URL}/roles", auth=HTTPBasicAuth(*st.session_state.auth), timeout=10)
                    if rr.ok:
                        roles = rr.json().get("roles", [])
                        st.session_state.roles = roles
                except Exception:
                    roles = []

            # Fetch users
            try:
                users_res = requests.get(f"{API_URL}/debug/users", auth=HTTPBasicAuth(*st.session_state.auth), timeout=30)
                users = users_res.json().get("users", []) if users_res.ok else []
            except Exception:
                users = []

            # Fetch documents
            try:
                docs_res = requests.get(f"{API_URL}/debug/docs", auth=HTTPBasicAuth(*st.session_state.auth), timeout=30)
                docs = docs_res.json().get("documents", []) if docs_res.ok else []
            except Exception:
                docs = []

            st.markdown("### Users")
            if users:
                # Build list of dicts; show only username and role columns
                users_table = [{"users": u.get('username'), "roles": u.get('role')} for u in users]
                st.table(users_table)
                # CSV download with columns: users, roles
                import csv, io
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["users", "roles"])
                for u in users:
                    writer.writerow([u.get('username'), u.get('role')])
                st.download_button("Download users CSV", data=buf.getvalue(), file_name="users.csv", mime="text/csv")
            else:
                st.info("No users found or failed to fetch users.")

            st.markdown("### Documents")

            # Role filter control: normalize and dedupe roles (case-insensitive) to avoid duplicates like 'finance' and 'Finance'
            def _normalize_roles(raw_roles):
                seen = set()
                out = []
                for r in raw_roles:
                    if not r:
                        continue
                    rl = str(r).strip()
                    key = rl.lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(rl)
                return out

            if roles:
                roles_clean = _normalize_roles(roles)
            else:
                roles_from_docs = [d.get('role') for d in docs if d.get('role')]
                roles_clean = _normalize_roles(roles_from_docs)

            filter_roles = ["All"] + roles_clean
            selected_role = st.selectbox("Filter documents by role", options=filter_roles)

            # Filter documents based on selected role
            if selected_role == "All":
                filtered_docs = docs
            else:
                filtered_docs = [d for d in docs if str(d.get('role', '')).lower() == str(selected_role).lower()]

            # De-duplicate documents by filepath (fallback to filename)
            seen = set()
            unique_filtered_docs = []
            for d in filtered_docs:
                key = (d.get('filepath') or d.get('filename') or '').strip()
                if not key:
                    # If no filepath available, use id+filename as fallback
                    key = f"{d.get('id')}-{d.get('filename')}"
                if key not in seen:
                    seen.add(key)
                    unique_filtered_docs.append(d)

            if unique_filtered_docs:
                # Present documents in a nicer table-like layout
                for d in unique_filtered_docs:
                    st.markdown(f"**{d.get('filename')}** — Role: `{d.get('role')}`")
                    st.caption(d.get('filepath'))
                    # Download link
                    download_url = f"{API_URL}/download-doc/{d.get('id')}"
                    st.markdown(f"[Download]({download_url})")
                    st.markdown("---")

                # CSV download for filtered (unique) documents
                import csv, io
                buf2 = io.StringIO()
                writer2 = csv.writer(buf2)
                writer2.writerow(["id", "filename", "role", "filepath", "headers", "embedded"])
                for d in unique_filtered_docs:
                    writer2.writerow([d.get('id'), d.get('filename'), d.get('role'), d.get('filepath'), d.get('headers'), d.get('embedded')])
                st.download_button("Download documents CSV", data=buf2.getvalue(), file_name="documents.csv", mime="text/csv")
            else:
                st.info("No documents found for the selected role.")

   
