import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import base64

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
        with st.spinner("Authenticating, please wait..."):
            res = requests.get(f"{API_URL}/login", auth=HTTPBasicAuth(username, password))
        if res.status_code == 200:
            st.session_state.auth = (username, password)
            st.session_state.username = username
            st.session_state.password = password
            st.session_state.role = res.json()["role"]
            # Save credentials to localStorage for auto-login
            st.markdown(f"""
            <script>
            localStorage.setItem('fs_username', '{username}');
            localStorage.setItem('fs_password', '{password}');
            </script>
            """, unsafe_allow_html=True)
            # Fetch roles once login is successful
            with st.spinner("Loading roles..."):
                st.session_state.roles = fetch_roles()
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
            st.session_state.auth = None
            st.session_state.role = None
            st.session_state.page = "login"
            st.rerun()
    
        # Role-specific section
        # Dynamic rendering
    with left_col:
        st.markdown("")
        if role == "C-Level":
            st.write("You have global access")
            tab1, tab2, tab3 = st.tabs(["💬 Chat", "🧾 Upload (C-Level)", "👤 Admin (C-Level)"])
        
        elif role == "General":
            st.write(f"You have access to documents and features related to the `{role}` role.")
            (tab1,) = st.tabs(["💬 Chat"])

        else:
            st.write(f"You have access to documents and features related to the `{role}` role.")
            st.markdown("You also have access to **General documents** (e.g.,regulations, company policies, holidays, announcements)")
            (tab1,) = st.tabs(["💬 Chat"])
    
 
    # --- Chat Tab ---
    with tab1:
        st.subheader("Ask a question:")
        question = st.text_input("Your Question")
        if st.button("Submit"):
            with st.spinner("Getting answer from backend..."):
                res = requests.post(
                    f"{API_URL}/chat",
                    json={"question": question, "role": st.session_state.role, "detail": "brief"},
                    auth=HTTPBasicAuth(*st.session_state.auth)
                )
            st.markdown("**Answer:**")
            if res.status_code == 200:
                st.success("✅ Answer:")
                answer = res.json()["answer"]
                st.write(answer)
                # Save last question/answer in session for expansion
                st.session_state._last_q = question
                st.session_state._last_answer = answer
            else:
                st.error("❌ Something went wrong while processing your question.")

        # Allow user to expand the last answer
        if "_last_q" in st.session_state:
            if st.button("Expand Answer"):
                with st.spinner("Requesting extended answer..."):
                    q = st.session_state._last_q
                    res2 = requests.post(
                        f"{API_URL}/chat",
                        json={"question": q, "role": st.session_state.role, "detail": "extended"},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                if res2.status_code == 200:
                    extended = res2.json()["answer"]
                    st.info("🔎 Extended Answer:")
                    st.write(extended)
                    st.session_state._last_answer = extended
                else:
                    st.error("❌ Failed to get extended answer.")
        
            

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
            doc_file = st.file_uploader("Upload document (.md or .csv)", type=["csv", "md"])

            
            if st.button("Upload Document") and doc_file:
                with st.spinner("Uploading document, please wait..."):
                    res = requests.post(
                        f"{API_URL}/upload-docs",
                        files={"file": doc_file},
                        data={"role": selected_role},
                        auth=HTTPBasicAuth(*st.session_state.auth)
                    )
                if res.ok:
                    st.success(res.json()["message"])
                else:
                    st.error(res.json().get("detail", "Something went wrong."))

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

   
