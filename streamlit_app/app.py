import streamlit as st
from utils.api_client import login_user

# Configuration de la page
st.set_page_config(page_title="KU Screening System", layout="centered")

st.title("🎓 PG Applicant Screening System")
st.write("System online — Khalifa University")

# --- LOGIQUE DE CONNEXION ---
if "token" not in st.session_state:
    st.subheader("🔐 Login Required")
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="admin@ku.ac.ae")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            status, res = login_user(email, password)
            if status == 200:
                st.session_state.token = res["access_token"]
                st.success("Login successful! Use the sidebar to navigate.")
                st.rerun() # Rafraîchit la page pour cacher le formulaire
            else:
                st.error(f"Login failed: {res.get('detail', 'Unknown error')}")
else:
    # Ce qui s'affiche une fois connecté
    st.success("✅ You are logged in.")
    st.info("Use the sidebar on the left to access Upload, Dashboard, and Ranking.")
    
    if st.button("Logout"):
        del st.session_state.token
        st.rerun()