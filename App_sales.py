import os
import re

import psycopg2
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta, date
from urllib.parse import quote as urlquote
import pandas as pd
import numpy as np
import hashlib
import time

st.set_page_config(
    page_title="Store Tracker",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": "Mobile-friendly Store Tracker v3.3 - per-user inventory & sales tracking with monthly AI insights, manager approvals, WhatsApp receipts and Supabase Postgres persistence. Contact your manager for account help."
    }
)

# ------------------------------------------------------------------
# 0. CONFIG
# ------------------------------------------------------------------
CURRENCY = "GH₵"                   
SESSION_TIMEOUT_MINUTES = 30       

MANAGER_SECRET = (
    os.environ.get("MANAGER_SECRET", "").strip()
    or st.secrets.get("MANAGER_SECRET", "").strip()
)

DB_URL = (
    os.environ.get("SUPABASE_DB_URL", "").strip()
    or st.secrets.get("SUPABASE_DB_URL", "").strip()
)

if not DB_URL:
    st.error(
        "Database is not configured. Set SUPABASE_DB_URL in Streamlit Secrets "
        "(cloud) or as an environment variable (local)."
    )
    st.stop()

try:
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
except psycopg2.OperationalError as e:
    st.error("Could not connect to the database. Check SUPABASE_DB_URL. Details: " + str(e))
    st.stop()



try:
    from passlib.hash import bcrypt as _bcrypt
    PASSLIB_AVAILABLE = True
except ImportError:
    PASSLIB_AVAILABLE = False

def hash_password(password):
    if PASSLIB_AVAILABLE:
        return _bcrypt.hash(password)
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, stored_hash):
    """Verify against bcrypt or legacy SHA-256."""
    if stored_hash.startswith("$2"):
        if not PASSLIB_AVAILABLE:
            return False, False
        try:
            return _bcrypt.verify(password, stored_hash), False
        except ValueError:
            return False, False
    legacy_match = hashlib.sha256(password.encode()).hexdigest() == stored_hash
    return legacy_match, legacy_match 

# ------------------------------------------------------------------
# OPTIONAL: Random Forest (AI Agent)
# ------------------------------------------------------------------
try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import LabelEncoder
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ------------------------------------------------------------------
# 1. MOBILE-RESPONSIVE CSS
# ------------------------------------------------------------------
st.markdown("""
<style>
    html, body {
        overflow-x: hidden !important;
        max-width: 100vw !important;
    }
    .stApp {
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    .block-container {
        max-width: 100% !important;
    }
    
    p, span, div {
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    
    [data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {
        max-width: 100% !important;
        overflow-x: auto !important;
    }
    /* the date-range filter often causes the page to stretch on mobile */
    [data-testid="stDateInput"] {
        max-width: 100% !important;
    }

    @media (max-width: 768px) {
        .stApp {
            max-width: 100vw !important;
            padding: 0.4rem !important;
        }
        .stButton>button {
            width: 100% !important;
            margin-bottom: 0.5rem !important;
            min-height: 46px !important;
            font-size: 16px !important;
        }
        h1 { font-size: 1.4rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.05rem !important; }
        .stSelectbox, .stNumberInput, .stTextInput {
            width: 100% !important;
        }
        [data-testid="stSidebar"] {
            min-width: 200px !important;
            max-width: 240px !important;
        }
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        [data-testid="stMetric"] {
            padding: 0.3rem 0.2rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.05rem !important;
        }
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 100%;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;   
    }
    
    .product-text { color: #C2185B; font-weight: 700; }
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    div[data-testid="stSelectbox"] [data-baseweb="select"] span {
        color: #C2185B !important;
        font-weight: 600;
    }
    .stock-badge {
        background: #ffffff;
        padding: 0.6rem 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #2196F3;
        margin: 0.6rem 0;
        font-size: 1rem;
        color: #333333;
    }
    .out-of-stock {
        border-left-color: #b71c1c !important;
        background: #ff5252 !important;
        color: #ffffff !important;
    }
     .low-stock {
        border-left-color: #009688 !important;
        background: #e0f2f1 !important;
    }
    .inventory-card {
        border-left: 5px solid #4CAF50;
        padding: 0.6rem 1rem;
        margin: 0.6rem 0;
        background: linear-gradient(90deg, #e8f5e9 0%, #ffffff 100%);
        border-radius: 0.5rem;
        font-size: 1rem;
        color: #333333;
   }
    .auth-card {
        max-width: 420px;
        margin: 2rem auto;
        padding: 1.5rem;
        background: #1e1e2e;
        color:#ffffff;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        border: 1px solid #2d2d44;
    }
    .welcome-banner {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        text-align: center;
    }

     .metric-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.6rem;
        margin: 0.8rem 0;
    }
    @media (min-width: 769px) {
        .metric-grid { grid-template-columns: repeat(4, 1fr); }
    }
    .metric-card {
        padding: 0.8rem 1rem;
        border-radius: 12px;
        color: #ffffff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }
    .metric-card .metric-label { font-size: 0.72rem; opacity: 0.9; margin-bottom: 0.2rem; }
    .metric-card .metric-value { font-size: 1.2rem; font-weight: 700; word-wrap: break-word; }
    .m-blue   { background: linear-gradient(135deg, #2196F3 0%, #21CBF3 100%); }
    .m-purple { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .m-green  { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
    .m-pink   { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
    
    .manager-badge {
        background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: bold;
        display: inline-block;
        margin-left: 0.5rem;
    }
    .wa-receipt-btn {
        display: inline-block;
        padding: 0.6rem 1.2rem;
        background: #25D366;
        color: #ffffff !important;
        border-radius: 8px;
        text-decoration: none;
        font-weight: 600;
        margin-top: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. DATABASE SETUP (Supabase Postgres - persistent across reboots)
# ------------------------------------------------------------------
cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        product_name TEXT NOT NULL,
        total_quantity INTEGER,
        quantity_sold INTEGER DEFAULT 0,
        owner TEXT DEFAULT 'admin',
        PRIMARY KEY (product_name, owner)
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        customer_name TEXT,
        phone_number TEXT,
        product_name TEXT,
        amount_paid REAL,
        quantity_bought INTEGER,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        recorded_by TEXT DEFAULT 'admin',
        owner TEXT DEFAULT 'admin'
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT,
        phone TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS managers (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# New registrations start as 'pending' (manager must approve)
#cursor.execute("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'pending'")

# Case-insensitive usernames
cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username))")
cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_managers_username_lower ON managers (LOWER(username))")

conn.commit()

# ------------------------------------------------------------------
# 3. AUTH HELPERS
# ------------------------------------------------------------------
def init_session():
    defaults = {
        "logged_in": False,
        "user_role": None,
        "username": None,
        "first_name": None,
        "user_id": None,
        "auth_page": "login",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

def login_user(username, password, role="user"):
    username = username.strip().lower()
    if role == "manager":
        cursor.execute("SELECT id, first_name, password_hash FROM managers WHERE LOWER(username) = %s", (username,))
        row = cursor.fetchone()
        status = 'active'
    else:
        cursor.execute("SELECT id, first_name, password_hash, status FROM users WHERE LOWER(username) = %s", (username,))
        row = cursor.fetchone()
        status = row[3] if row else None

    if not row:
        return False
    if status == 'blocked':
        return "blocked"
    if status == 'pending':
        return "pending"

    ok, needs_upgrade = verify_password(password, row[2])
    if not ok:
        return False

    if needs_upgrade:  
        cursor.execute("UPDATE " + ("managers" if role == "manager" else "users") +
                       " SET password_hash = %s WHERE id = %s", (hash_password(password), row[0]))
        conn.commit()

    st.session_state.logged_in = True
    st.session_state.user_role = role
    st.session_state.username = username
    st.session_state.first_name = row[1]
    st.session_state.user_id = row[0]
    st.session_state.last_activity = datetime.now()
    return True

def check_session_timeout():
    """Auto-logout after SESSION_TIMEOUT_MINUTES of inactivity."""
    if not st.session_state.logged_in:
        return
    last = st.session_state.get("last_activity")
    if last and (datetime.now() - last).total_seconds() > SESSION_TIMEOUT_MINUTES * 60:
        logout()
    st.session_state.last_activity = datetime.now()

def logout():
    for k in ["logged_in", "user_role", "username", "first_name", "user_id", "auth_page", "last_activity"]:
        st.session_state[k] = None if k != "auth_page" else "login"
    st.session_state.logged_in = False
    st.session_state.auth_page = "login"
    st.rerun()

def register_user(username, password, first_name, last_name="", phone=""):
    try:
        pw_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO users (username, password_hash, first_name, last_name, phone, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (username.strip().lower(), pw_hash, first_name, last_name, phone))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False

def register_manager(username, password, first_name, last_name=""):
    try:
        pw_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO managers (username, password_hash, first_name, last_name)
            VALUES (%s, %s, %s, %s)
        """, (username.strip().lower(), pw_hash, first_name, last_name))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False

# Narrow & center the login/register pages on desktop (only rendered when logged out)
AUTH_CSS = """
<style>
    .block-container {
        max-width: 460px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 3rem !important;
    }
    .auth-card {
        max-width: 420px !important;
        margin: 0 auto !important;
    }
    /* Hide the default Streamlit menu (Rerun/Settings/Print/About) on login/register pages */
    #MainMenu {display: none !important;}
    [data-testid="stMainMenu"] {display: none !important;}
</style>
"""

# ------------------------------------------------------------------
# 4. AUTHENTICATION PAGES
# ------------------------------------------------------------------
def show_login_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)
    st.header("Login")

    tab1, tab2 = st.tabs(["User Login", "Manager Login"])

    with tab1:
        with st.form("user_login_form"):
            u = st.text_input("Username", key="ul_user")
            p = st.text_input("Password", type="password", key="ul_pass")
            c1, c2 = st.columns(2)
            with c1:
                submitted = st.form_submit_button("Sign In", use_container_width=True)
            with c2:
                switch = st.form_submit_button("Create Account", use_container_width=True)
            if submitted:
                login_result = login_user(u, p, role="user")
                if login_result is True:
                    with st.spinner("Logging in... Please wait"):
                        time.sleep(2.5)
                    st.success("Welcome back!")
                    st.rerun()
                elif login_result == "blocked":
                    st.error("This account has been blocked. Please contact the manager.")
                elif login_result == "pending":
                    st.warning("Your account is awaiting manager approval. You'll be able to log in once a manager approves it.")
                else:
                    st.error("Invalid username or password.")
            if switch:
                st.session_state.auth_page = "register"
                st.rerun()

    with tab2:
        with st.form("manager_login_form"):
            u = st.text_input("Manager Username", key="ml_user")
            p = st.text_input("Manager Password", type="password", key="ml_pass")
            c1, c2 = st.columns(2)
            with c1:
                submitted = st.form_submit_button("Manager Sign In", use_container_width=True)
            with c2:
                switch = st.form_submit_button("Register Manager", use_container_width=True)
            if submitted:
                if login_user(u, p, role="manager"):
                    with st.spinner("Logging in... Please wait"):
                        time.sleep(2.5)
                    st.success("Welcome back, Manager!")
                    st.rerun()
                else:
                    st.error("Invalid manager credentials.")
            if switch:
                st.session_state.auth_page = "register_manager"
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

def show_register_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)
    st.header("Create User Account")
    st.info("New accounts need manager approval before you can log in.")
    with st.form("register_form"):
        fn = st.text_input("First Name *", key="reg_fn")
        ln = st.text_input("Last Name", key="reg_ln")
        phone = st.text_input("Phone Number", key="reg_phone")
        un = st.text_input("Username *", key="reg_un")
        pw = st.text_input("Password *", type="password", key="reg_pw")
        pw2 = st.text_input("Confirm Password *", type="password", key="reg_pw2")

        c1, c2 = st.columns(2)
        with c1:
            submitted = st.form_submit_button("Register", use_container_width=True)
        with c2:
            back = st.form_submit_button("Back to Login", use_container_width=True)

        if submitted:
            if not fn or not un or not pw:
                st.error("Please fill in all required fields (*).")
            elif pw != pw2:
                st.error("Passwords do not match!")
            elif len(pw) < 4:
                st.error("Password must be at least 4 characters.")
            else:
                if register_user(un, pw, fn, ln, phone):
                    st.success("Account created! It will be active once a manager approves it.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.error("Username already exists. Please choose another.")
        if back:
            st.session_state.auth_page = "login"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def show_manager_register_page():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="auth-card">', unsafe_allow_html=True)
    st.header("Create Manager Account")
    st.info("Manager accounts have full access to view all user accounts and system data.")
    if not MANAGER_SECRET:
        st.error("WARNING: MANAGER_SECRET environment variable is not set. Manager registration is disabled.")
    with st.form("manager_register_form"):
        fn = st.text_input("First Name *", key="mreg_fn")
        ln = st.text_input("Last Name", key="mreg_ln")
        un = st.text_input("Manager Username *", key="mreg_un")
        pw = st.text_input("Password *", type="password", key="mreg_pw")
        pw2 = st.text_input("Confirm Password *", type="password", key="mreg_pw2")
        secret = st.text_input("Manager Secret Key *", type="password", key="mreg_secret",
                               help="Enter the secret key to authorize manager registration.")

        c1, c2 = st.columns(2)
        with c1:
            submitted = st.form_submit_button("Register Manager", use_container_width=True)
        with c2:
            back = st.form_submit_button("Back to Login", use_container_width=True)

        if submitted:
            if not fn or not un or not pw or not secret:
                st.error("Please fill in all required fields (*).")
            elif pw != pw2:
                st.error("Passwords do not match!")
            elif len(pw) < 4:
                st.error("Password must be at least 4 characters.")
            elif secret.strip() != MANAGER_SECRET.strip():
                st.error("Invalid manager secret key! Contact your administrator.")
            else:
                if register_manager(un, pw, fn, ln):
                    st.success("Manager account created! Please log in.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.error("Username already exists. Please choose another.")
        if back:
            st.session_state.auth_page = "login"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. MANAGER DASHBOARD
# ------------------------------------------------------------------
def show_manager_dashboard():
    st.header("Manager Dashboard")
    st.markdown("Welcome, **" + st.session_state.first_name + "** <span class='manager-badge'>MANAGER</span>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["User Accounts", "All Sales", "System Reset"])

    with tab1:
        # ---- Pending approvals (shown first) ----
        cursor.execute("SELECT id, username, first_name, last_name, phone, created_at FROM users WHERE status = 'pending' ORDER BY created_at")
        pending = cursor.fetchall()
        if pending:
            st.warning(" " + str(len(pending)) + " account(s) awaiting your approval")
            for p in pending:
                cols = st.columns([3, 1, 1])
                with cols[0]:
                    st.write("**" + p[1] + "** — " + (p[2] or "") + " " + (p[3] or "") + ((" | " + p[4]) if p[4] else ""))
                with cols[1]:
                    if st.button("Approve", key="approve_" + str(p[0]), use_container_width=True):
                        cursor.execute("UPDATE users SET status = 'active' WHERE id = %s", (p[0],))
                        conn.commit()
                        st.success("Approved '" + p[1] + "'.")
                        st.rerun()
                with cols[2]:
                    if st.button("Reject", key="reject_" + str(p[0]), use_container_width=True):
                        cursor.execute("DELETE FROM users WHERE id = %s", (p[0],))
                        conn.commit()
                        st.info("Rejected and removed '" + p[1] + "'.")
                        st.rerun()
            st.markdown("---")

        st.subheader("All Registered User Accounts")
        cursor.execute("SELECT id, username, first_name, last_name, phone, created_at, status FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        if users:
            df = pd.DataFrame(users, columns=["ID", "Username", "First Name", "Last Name", "Phone", "Created At", "Status"])
            st.dataframe(df, use_container_width=True)
            st.caption("Total user accounts: " + str(len(users)))

            st.markdown("---")
            st.subheader("Manage an Account")
            user_map = {u[1]: u for u in users}  
            selected_username = st.selectbox("Select user account to manage", options=list(user_map.keys()))
            sel = user_map[selected_username]
            sel_status = sel[6] if sel[6] else "active"

            c1, c2 = st.columns(2)
            with c1:
                if sel_status == 'blocked':
                    if st.button("Unblock Account", use_container_width=True):
                        cursor.execute("UPDATE users SET status = 'active' WHERE username = %s", (selected_username,))
                        conn.commit()
                        st.success("Account '" + selected_username + "' has been unblocked.")
                        st.rerun()
                else:
                    if st.button("Block Account", use_container_width=True):
                        cursor.execute("UPDATE users SET status = 'blocked' WHERE username = %s", (selected_username,))
                        conn.commit()
                        st.warning("Account '" + selected_username + "' has been blocked. They can no longer log in.")
                        st.rerun()
            with c2:
                if st.button("Delete Account", use_container_width=True):
                    st.session_state.confirm_delete_user = selected_username

            if st.session_state.get("confirm_delete_user"):
                target = st.session_state.confirm_delete_user
                st.error("Deleting account '" + target + "'. Type DELETE to confirm.")
                del_data = st.checkbox("Also permanently delete this user's products, sales and inventory records", value=False)
                confirm = st.text_input("Confirmation", key="confirm_delete_user_text")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Confirm Delete", use_container_width=True):
                        if confirm == "DELETE":
                            if del_data:
                                cursor.execute("DELETE FROM sales WHERE owner = %s", (target,))
                                cursor.execute("DELETE FROM inventory WHERE owner = %s", (target,))
                            cursor.execute("DELETE FROM users WHERE username = %s", (target,))
                            conn.commit()
                            st.session_state.confirm_delete_user = None
                            st.success("Account '" + target + "' has been deleted.")
                            st.rerun()
                        else:
                            st.error("Confirmation text mismatch.")
                with c2:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state.confirm_delete_user = None
                        st.rerun()

            st.markdown("---")
            st.subheader("Reset User Password")
            st.caption("Set a new password for '" + selected_username + "'. Share it with the user in person or over a trusted channel.")
            new_pw = st.text_input("New Password", type="password", key="mgr_reset_pw")
            new_pw2 = st.text_input("Confirm New Password", type="password", key="mgr_reset_pw2")
            if st.button("Reset Password", use_container_width=True):
                if not new_pw:
                    st.error("Please enter a new password.")
                elif new_pw != new_pw2:
                    st.error("Passwords do not match!")
                elif len(new_pw) < 4:
                    st.error("Password must be at least 4 characters.")
                else:
                    cursor.execute("UPDATE users SET password_hash = %s WHERE username = %s",
                                   (hash_password(new_pw), selected_username))
                    conn.commit()
                    st.success("Password for '" + selected_username + "' has been reset. They can now log in with the new password.")
        else:
            st.info("No user accounts registered yet.")

    with tab2:
        st.subheader("All Sales Records (System-wide)")
        cursor.execute("""
            SELECT s.id, s.customer_name, s.phone_number, s.product_name, s.amount_paid,
                   s.quantity_bought, s.sale_date, s.recorded_by
            FROM sales s ORDER BY s.sale_date DESC
        """)
        sales = cursor.fetchall()
        if sales:
            df = pd.DataFrame(sales, columns=["ID", "Customer", "Phone", "Product", "Amount", "Qty", "Date/Time", "Recorded By"])
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "Download all sales as CSV",
                df.to_csv(index=False).encode("utf-8"),
                "all_sales.csv",
                "text/csv",
                key="dl_all_sales"
            )
        else:
            st.info("No sales recorded yet.")

    with tab3:
        st.subheader("Danger Zone")
        st.warning("These actions affect the entire system and cannot be undone.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Delete ALL Sales", use_container_width=True):
                st.session_state.confirm_delete_sales = True
        with col2:
            if st.button("Delete ALL Inventory", use_container_width=True):
                st.session_state.confirm_delete_inventory = True

        if st.session_state.get("confirm_delete_sales"):
            st.error("Type DELETE ALL SALES to confirm")
            confirm = st.text_input("Confirmation", key="confirm_sales_text")
            if st.button("Confirm Delete Sales"):
                if confirm == "DELETE ALL SALES":
                    cursor.execute("DELETE FROM sales")
                    cursor.execute("UPDATE inventory SET quantity_sold = 0")
                    conn.commit()
                    st.success("All sales deleted.")
                    st.session_state.confirm_delete_sales = False
                    st.rerun()
                else:
                    st.error("Confirmation text mismatch.")

        if st.session_state.get("confirm_delete_inventory"):
            st.error("Type DELETE ALL INVENTORY to confirm")
            confirm = st.text_input("Confirmation", key="confirm_inv_text")
            if st.button("Confirm Delete Inventory"):
                if confirm == "DELETE ALL INVENTORY":
                    cursor.execute("DELETE FROM inventory")
                    conn.commit()
                    st.success("All inventory deleted.")
                    st.session_state.confirm_delete_inventory = False
                    st.rerun()
                else:
                    st.error("Confirmation text mismatch.")

# ------------------------------------------------------------------
# 6. MAIN APP (after login)
# ------------------------------------------------------------------
def get_products():
    """Return products visible to the current user (all for manager, own only for users)."""
    if st.session_state.user_role == "manager":
        cursor.execute("SELECT product_name, total_quantity, quantity_sold FROM inventory ORDER BY product_name")
    else:
        cursor.execute("SELECT product_name, total_quantity, quantity_sold FROM inventory WHERE owner = %s ORDER BY product_name", (st.session_state.username,))
    return cursor.fetchall()

def get_sales(role, username):
    """Return sales visible to the current user."""
    if role == "manager":
        cursor.execute("""
            SELECT id, customer_name, phone_number, product_name, amount_paid, quantity_bought, sale_date, recorded_by
            FROM sales ORDER BY sale_date DESC, id DESC
        """)
    else:
        cursor.execute("""
            SELECT id, customer_name, phone_number, product_name, amount_paid, quantity_bought, sale_date, recorded_by
            FROM sales WHERE owner = %s ORDER BY sale_date DESC, id DESC
        """, (username,))
    return cursor.fetchall()

def whatsapp_url(phone, message):
    """Build a wa.me link; converts local Ghana 0xxxx numbers to 233xxx."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "233" + digits[1:]
    if len(digits) < 9:
        return None
    return "https://wa.me/" + digits + "?text=" + urlquote(message)

def show_main_app():
    check_session_timeout()

    role = st.session_state.user_role
    fname = st.session_state.first_name
    username = st.session_state.username

    if role == "manager":
        st.markdown('<div class="welcome-banner"><h3>Welcome, ' + fname + '! <span class="manager-badge">MANAGER</span></h3><p style="margin:0; opacity:0.9;">You have full system access.</p></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="welcome-banner"><h3>Welcome, ' + fname + '!</h3><p style="margin:0; opacity:0.9;">Ready to manage your store today?</p></div>', unsafe_allow_html=True)

    if role == "manager":
        menu = st.sidebar.selectbox(
            "Choose Action",
            ["Record Sale", "Manage Inventory", "View Stock & Sales", "Delete Records",
             "Monthly AI Insights", "Manager Dashboard"]
        )
    else:
        menu = st.sidebar.selectbox(
            "Choose Action",
            ["Record Sale", "Manage Inventory", "View Stock & Sales", "Delete Records", "Monthly AI Insights"]
        )

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", use_container_width=True):
        logout()

    # Regular users: keep the 3-dots menu but strip Rerun/Settings so only Print & About remain
    if role != "manager":
        components.html("""
        <script>
        (function() {
            var HIDE = /^(Rerun|Settings|Record a screencast|Clear cache|View app source|Report a bug|Developer options)/;
            var doc = window.parent.document;
            function scrub(root) {
                var els = (root || doc).querySelectorAll('li, [role="menuitem"], [role="option"]');
                for (var i = 0; i < els.length; i++) {
                    var t = (els[i].textContent || '').trim();
                    if (HIDE.test(t)) { els[i].style.display = 'none'; }
                }
            }
            var obs = new MutationObserver(function(muts) {
                for (var m = 0; m < muts.length; m++) {
                    for (var n = 0; n < muts[m].addedNodes.length; n++) {
                        if (muts[m].addedNodes[n].nodeType === 1) scrub(muts[m].addedNodes[n]);
                    }
                }
            });
            obs.observe(doc.body, {childList: true, subtree: true});
            scrub(doc.body);
        })();
        </script>
        """, height=0)

    # ==================================================================
    # MENU: RECORD SALE
    # ==================================================================
    if menu == "Record Sale":
        st.header("Record a Customer Purchase")
        products = get_products()

        if not products:
            st.warning("No products found! Please add products in the 'Manage Inventory' section first.")
        else:
            product_dict = {p[0]: (p[1] - p[2]) for p in products}

            selected_product = st.selectbox(
                "Select Product",
                list(product_dict.keys()),
                key="sale_product_select"
            )

            remaining_stock = product_dict[selected_product]
            prod_html = '<span class="product-text">' + selected_product + '</span>'
            if remaining_stock <= 0:
                st.markdown('<div class="stock-badge out-of-stock">OUT OF STOCK: ' + prod_html + ' | Available: <b>' + str(remaining_stock) + '</b></div>', unsafe_allow_html=True)
            elif remaining_stock <= 5:
                st.markdown('<div class="stock-badge low-stock">LOW STOCK: ' + prod_html + ' | Available: <b>' + str(remaining_stock) + '</b></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="stock-badge">' + prod_html + ' | Available: <b>' + str(remaining_stock) + '</b> units</div>', unsafe_allow_html=True)

            with st.form("sale_form", clear_on_submit=True):
                c_name = st.text_input("Customer Name", key="sale_name")
                phone = st.text_input("Phone Number", key="sale_phone")
                amount = st.number_input("Amount Bought (" + CURRENCY + ")", min_value=0.0, step=0.5, key="sale_amount")
                qty = st.number_input("Quantity Bought", min_value=1, step=1, key="sale_qty")

                col1, col2 = st.columns(2)
                with col1:
                    submit_sale = st.form_submit_button("Save Sale", use_container_width=True)
                with col2:
                    reset_sale = st.form_submit_button("Reset Form", use_container_width=True)

                if submit_sale:
                    if not c_name or not phone:
                        st.error("Please provide the customer's name and phone number.")
                    elif qty > remaining_stock:
                        st.error("Not enough stock! Only " + str(remaining_stock) + " left for " + selected_product + ".")
                    else:
                        cursor.execute("""
                            SELECT id FROM sales
                            WHERE customer_name = %s AND product_name = %s AND amount_paid = %s
                            AND quantity_bought = %s AND owner = %s AND sale_date > NOW() - INTERVAL '2 minutes'
                        """, (c_name, selected_product, amount, qty, username))
                        dup = cursor.fetchone()

                        if dup:
                            st.warning("Duplicate Alert: This exact sale was recorded just moments ago!")
                        else:
                            recorder = username
                            cursor.execute("""
                                INSERT INTO sales (customer_name, phone_number, product_name, amount_paid, quantity_bought, sale_date, recorded_by, owner)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (c_name, phone, selected_product, amount, qty, datetime.now(), recorder, username))
                            cursor.execute("""
                                UPDATE inventory SET quantity_sold = quantity_sold + %s WHERE product_name = %s AND owner = %s
                            """, (qty, selected_product, username))
                            conn.commit()
                            st.success("Sale for " + c_name + " recorded successfully!")

                            wa = whatsapp_url(phone, (
                                "Hello " + c_name + "! Thank you for your purchase.\n"
                                + str(qty) + "x " + selected_product + "\n"
                                + "Total: " + CURRENCY + str(amount) + "\n"
                                + "Date: " + datetime.now().strftime("%Y-%m-%d %H:%M")
                            ))
                            if wa:
                                st.markdown('<a class="wa-receipt-btn" href="' + wa + '" target="_blank">Send receipt to customer on WhatsApp</a>', unsafe_allow_html=True)
                            else:
                                st.caption("WhatsApp receipt unavailable: phone number format not recognized.")

                if reset_sale:
                    # clear_on_submit=True already clears the widget values on any form submit.
                    st.rerun()

    # ==================================================================
    # MENU: MANAGE INVENTORY
    # ==================================================================
    elif menu == "Manage Inventory":
        st.header("Add New Product or Restock")
        with st.form("inventory_form", clear_on_submit=True):
            prod_name = st.text_input("Product Name", key="inv_name")
            add_qty = st.number_input("Total Quantity to Add", min_value=1, step=1, key="inv_qty")

            col1, col2 = st.columns(2)
            with col1:
                submit_inv = st.form_submit_button("Add / Update Product", use_container_width=True)
            with col2:
                reset_inv = st.form_submit_button("Reset Form", use_container_width=True)

            if submit_inv:
                if not prod_name:
                    st.error("Please enter a product name.")
                else:
                    cursor.execute("""
                        SELECT total_quantity FROM inventory WHERE LOWER(product_name) = LOWER(%s) AND owner = %s
                    """, (prod_name, username))
                    existing = cursor.fetchone()

                    if existing:
                        st.warning("'" + prod_name + "' already exists with " + str(existing[0]) + " units! Adding to existing stock.")
                        new_total = existing[0] + add_qty
                        cursor.execute("""
                            UPDATE inventory SET total_quantity = %s WHERE LOWER(product_name) = LOWER(%s) AND owner = %s
                        """, (new_total, prod_name, username))
                        conn.commit()
                        st.success("Updated '" + prod_name + "' total quantity to " + str(new_total) + "!")
                    else:
                        cursor.execute("""
                            INSERT INTO inventory (product_name, total_quantity, quantity_sold, owner)
                            VALUES (%s, %s, 0, %s)
                        """, (prod_name, add_qty, username))
                        conn.commit()
                        st.success("New product '" + prod_name + "' added with " + str(add_qty) + " units!")

            if reset_inv:
                # clear_on_submit=True already clears the widget values on any form submit.
                st.rerun()

    # ==================================================================
    # MENU: VIEW STOCK & SALES (dashboard + alerts + search + CSV + edit/delete)
    # ==================================================================
    elif menu == "View Stock & Sales":
        stock_data = []
        if role == "manager":
            cursor.execute("""
                SELECT product_name, total_quantity, quantity_sold, (total_quantity - quantity_sold) as remaining
                FROM inventory
            """)
        else:
            cursor.execute("""
                SELECT product_name, total_quantity, quantity_sold, (total_quantity - quantity_sold) as remaining
                FROM inventory WHERE owner = %s
            """, (username,))
        stock_data = cursor.fetchall()

        sales_data = get_sales(role, username)

        # ---- Dashboard metrics ----
        st.header("Dashboard")
        today_rev = 0.0
        month_rev = 0.0
        top_customer = "—"
        if sales_data:
            today_d = date.today()
            month_s = today_d.strftime("%Y-%m")
            for s in sales_data:
                if s[6]:
                    if s[6].date() == today_d:
                        today_rev += s[4] or 0
                    if s[6].strftime("%Y-%m") == month_s:
                        month_rev += s[4] or 0
            spend = {}
            for s in sales_data:
                spend[s[1]] = spend.get(s[1], 0) + (s[4] or 0)
            if spend:
                best_c = max(spend, key=spend.get)
                top_customer = best_c + " (" + CURRENCY + str(int(round(spend[best_c]))) + ")"

        cards_html = '<div class="metric-grid">'
        cards_html += '<div class="metric-card m-blue"><div class="metric-label">Today\'s Revenue</div><div class="metric-value">' + CURRENCY + str(round(today_rev, 2)) + '</div></div>'
        cards_html += '<div class="metric-card m-purple"><div class="metric-label">This Month\'s Revenue</div><div class="metric-value">' + CURRENCY + str(round(month_rev, 2)) + '</div></div>'
        cards_html += '<div class="metric-card m-green"><div class="metric-label">Total Sales Recorded</div><div class="metric-value">' + str(len(sales_data)) + '</div></div>'
        cards_html += '<div class="metric-card m-pink"><div class="metric-label">Top Customer</div><div class="metric-value">' + top_customer + '</div></div>'
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)

        # ---- Low stock alerts ----
        low_items = [r for r in stock_data if r[3] <= 5]
        if low_items:
            st.subheader("Low Stock Alerts")
            month_s = date.today().strftime("%Y-%m")
            for r in low_items:
                sold_this_month = 0
                for s in sales_data:
                    if s[3] == r[0] and s[6] and s[6].strftime("%Y-%m") == month_s:
                        sold_this_month += s[5] or 0
                suggested = max(sold_this_month * 2 - r[3], 10)
                status_txt = "OUT OF STOCK" if r[3] <= 0 else "LOW STOCK"
                card_class = "stock-badge out-of-stock" if r[3] <= 0 else "stock-badge low-stock"
                st.markdown('<div class="' + card_class + '"><b style="color:#d32f2f;">' + r[0] + '</b> — ' + status_txt + ' | Remaining: <b style="color:#e65100;">' + str(r[3]) + '</b> | Suggested restock: <b style="color:#2e7d32;">' + str(suggested) + ' units</b></div>', unsafe_allow_html=True)
        else:
                st.success("All products are well stocked.")

        # ---- Inventory status ----
        st.header("Current Inventory Status")
        if stock_data:
            for row in stock_data:
                rem = row[3]
                if rem <= 0:
                    color, status = "#f44336", "OUT OF STOCK"
                elif rem <= 5:
                    color, status = "#ff9800", "LOW STOCK"
                else:
                    color, status = "#4CAF50", "OK"
                st.markdown('<div class="inventory-card" style="border-left-color: ' + color + ';"><b style="font-size:1.1rem;" class="product-text">' + row[0] + '</b><br>Total: ' + str(row[1]) + ' | Sold: ' + str(row[2]) + ' | <span style="color:' + color + '; font-weight:bold;">Remaining: ' + str(rem) + '</span> <span style="color:' + color + '; font-size:0.85rem;">(' + status + ')</span></div>', unsafe_allow_html=True)
        else:
            st.info("No inventory data available yet.")

        # ---- Sales log with search, date filter, CSV export ----
        st.header("Customer Sales Log")
        if sales_data:
            filtered = list(sales_data)

            q = st.text_input("Search customer, product or phone (optional)", key="sales_search").strip().lower()
            if q:
                filtered = [s for s in filtered if q in ((s[1] or "") + " " + (s[2] or "") + " " + (s[3] or "")).lower()]

            dates = [s[6].date() for s in sales_data if s[6]]
            if dates:
                dv = st.date_input("Filter by date (optional)", value=(min(dates), date.today()), key="sales_date_filter")
                if isinstance(dv, (list, tuple)) and len(dv) == 2:
                    d1, d2 = dv
                    filtered = [s for s in filtered if s[6] and d1 <= s[6].date() <= d2]
                elif hasattr(dv, "year"):
                    filtered = [s for s in filtered if s[6] and s[6].date() == dv]

            if filtered:
                df_sales = pd.DataFrame(
                    filtered,
                    columns=["ID", "Customer", "Phone", "Product", "Amount (" + CURRENCY + ")", "Qty", "Date/Time", "Recorded By"]
                )
                st.dataframe(df_sales, use_container_width=True)

                st.download_button(
                    "Download " + str(len(filtered)) + " sale(s) as CSV",
                    df_sales.to_csv(index=False).encode("utf-8"),
                    "sales_export.csv",
                    "text/csv",
                    key="dl_my_sales"
                )

                # ---- Edit a sale ----
                with st.expander("Edit a Sale Entry"):
                    edit_options = {}
                    for s in filtered:
                        label = "ID " + str(s[0]) + ": " + s[1] + " - " + s[3] + " (" + CURRENCY + str(s[4]) + ") | " + (str(s[6]) if s[6] else "N/A")
                        edit_options[label] = s
                    edit_sel = st.selectbox("Select sale to edit", options=list(edit_options.keys()), key="edit_sale_sel")
                    erow = edit_options[edit_sel]
                    with st.form("edit_sale_form"):
                        ec_name = st.text_input("Customer Name", value=erow[1] or "", key="edit_c")
                        e_phone = st.text_input("Phone Number", value=erow[2] or "", key="edit_p")
                        e_amount = st.number_input("Amount (" + CURRENCY + ")", min_value=0.0, value=float(erow[4] or 0), step=0.5, key="edit_a")
                        e_qty = st.number_input("Quantity Bought", min_value=1, value=int(erow[5] or 1), step=1, key="edit_q")
                        if st.form_submit_button("Save Changes", use_container_width=True):
                            prod_name, prod_owner, old_qty = erow[3], erow[7], int(erow[5] or 0)
                            cursor.execute("SELECT total_quantity, quantity_sold FROM inventory WHERE product_name = %s AND owner = %s", (prod_name, prod_owner))
                            inv = cursor.fetchone()
                            remaining = (inv[0] - inv[1]) if inv else 0
                            if e_qty > remaining + old_qty:
                                st.error("Not enough stock! Only " + str(remaining + old_qty) + " available for " + prod_name + " after returning the original " + str(old_qty) + " units.")
                            else:
                                cursor.execute("""
                                    UPDATE sales SET customer_name = %s, phone_number = %s, amount_paid = %s, quantity_bought = %s
                                    WHERE id = %s
                                """, (ec_name, e_phone, e_amount, e_qty, erow[0]))
                                cursor.execute("""
                                    UPDATE inventory SET quantity_sold = quantity_sold - %s + %s WHERE product_name = %s AND owner = %s
                                """, (old_qty, e_qty, prod_name, prod_owner))
                                conn.commit()
                                st.success("Sale ID " + str(erow[0]) + " updated and stock adjusted.")
                                st.rerun()

                # ---- Delete a sale ----
                st.markdown("---")
                st.subheader("Delete a Sale Entry")
                sale_options = {}
                for s in filtered:
                    label = "ID " + str(s[0]) + ": " + s[1] + " - " + s[3] + " (" + CURRENCY + str(s[4]) + ") | " + (str(s[6]) if s[6] else "N/A")
                    sale_options[label] = s[0]
                selected_option = st.selectbox("Select sale entry to remove", options=list(sale_options.keys()))

                if st.button("Delete Selected Sale", use_container_width=True):
                    sale_id_to_delete = sale_options[selected_option]
                    cursor.execute("SELECT product_name, quantity_bought, owner FROM sales WHERE id = %s", (sale_id_to_delete,))
                    sold_info = cursor.fetchone()
                    if sold_info:
                        cursor.execute("""
                            UPDATE inventory SET quantity_sold = quantity_sold - %s WHERE product_name = %s AND owner = %s
                        """, (sold_info[1], sold_info[0], sold_info[2]))
                    cursor.execute("DELETE FROM sales WHERE id = %s", (sale_id_to_delete,))
                    conn.commit()
                    st.success("Deleted sale entry (ID: " + str(sale_id_to_delete) + ") and restored stock!")
                    st.rerun()
            else:
                st.info("No sales match your search/filter.")
        else:
            st.info("No sales recorded yet.")

    # ==================================================================
    # MENU: DELETE RECORDS
    # ==================================================================
    elif menu == "Delete Records":
        st.header("Delete & Reset Records")

        st.subheader("Delete Individual Sale")
        sales_data = get_sales(role, username)

        if sales_data:
            sale_options = {}
            for s in sales_data:
                label = "ID " + str(s[0]) + ": " + s[1] + " bought " + str(s[4]) + "x " + s[2] + " for " + CURRENCY + str(s[3]) + " on " + (str(s[5]) if s[5] else "N/A")
                sale_options[label] = s[0]
            sel = st.selectbox("Select sale to delete", options=list(sale_options.keys()))
            if st.button("Delete Selected Sale", use_container_width=True):
                sid = sale_options[sel]
                cursor.execute("SELECT product_name, quantity_bought, owner FROM sales WHERE id = %s", (sid,))
                info = cursor.fetchone()
                if info:
                    cursor.execute("UPDATE inventory SET quantity_sold = quantity_sold - %s WHERE product_name = %s AND owner = %s",
                                   (info[1], info[0], info[2]))
                cursor.execute("DELETE FROM sales WHERE id = %s", (sid,))
                conn.commit()
                st.success("Deleted sale ID " + str(sid) + " and restored stock.")
                st.rerun()
        else:
            st.info("No sales available to delete.")

        st.markdown("---")
        st.subheader("Reset All Sales Data")
        if role == "manager":
            st.warning("This will permanently delete ALL sales records (all users) and reset sold quantities to 0.")
        else:
            st.warning("This will permanently delete YOUR sales records and reset your sold quantities to 0.")
        confirm_text = st.text_input("Type RESET to confirm clearing all sales", key="reset_confirm")
        if st.button("Clear All Sales History", use_container_width=True):
            if confirm_text == "RESET":
                if role == "manager":
                    cursor.execute("DELETE FROM sales")
                    cursor.execute("UPDATE inventory SET quantity_sold = 0")
                else:
                    cursor.execute("DELETE FROM sales WHERE owner = %s", (username,))
                    cursor.execute("UPDATE inventory SET quantity_sold = 0 WHERE owner = %s", (username,))
                conn.commit()
                st.success("All sales records cleared and inventory sold counts reset!")
                st.rerun()
            else:
                st.error("Confirmation text did not match. Please type RESET in all caps.")

    # ==================================================================
    # MENU: MONTHLY AI INSIGHTS
    # ==================================================================
    elif menu == "Monthly AI Insights":
        st.header("AI Sales Insights Agent")
        st.markdown("Predict next month's top & bottom products.")

        if not SKLEARN_AVAILABLE:
            st.error("scikit-learn is not installed. Run: pip install scikit-learn then restart the app.")
        else:
            data = []
            if role == "manager":
                cursor.execute("""
                    SELECT product_name, quantity_bought, sale_date
                    FROM sales WHERE sale_date IS NOT NULL
                """)
                data = cursor.fetchall()
            else:
                cursor.execute("""
                    SELECT product_name, quantity_bought, sale_date
                    FROM sales WHERE sale_date IS NOT NULL AND owner = %s
                """, (username,))
                data = cursor.fetchall()

            if len(data) < 5:
                st.info("Not enough sales data for AI analysis. Please record at least 5 sales with dates.")
            else:
                df = pd.DataFrame(data, columns=["product", "quantity", "date"])
                df["date"] = pd.to_datetime(df["date"])
                df["month"] = df["date"].dt.to_period("M").astype(str)
                df["month_num"] = df["date"].dt.month
                df["year"] = df["date"].dt.year

                st.subheader("Historical Monthly Summary")
                monthly = df.groupby(["month", "product"])["quantity"].sum().reset_index()
                st.dataframe(monthly, use_container_width=True)

                st.subheader("Actual Most & Least Purchased This Month")
                current_month = datetime.now().strftime("%Y-%m")
                this_month = df[df["month"] == current_month]
                if not this_month.empty:
                    prod_totals = this_month.groupby("product")["quantity"].sum().sort_values(ascending=False)
                    most = prod_totals.index[0]
                    least = prod_totals.index[-1]
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("Most Purchased", most, str(prod_totals.iloc[0]) + " units")
                    with c2:
                        st.metric("Least Purchased", least, str(prod_totals.iloc[-1]) + " units")
                else:
                    st.info("No sales recorded for the current month yet.")

                st.subheader("AI Prediction for Next Month")
                if st.button("Run Analysis", use_container_width=True):
                    with st.spinner("Training AI model on your sales history..."):
                        agg = df.groupby(["month", "product", "month_num"])["quantity"].sum().reset_index()
                        le = LabelEncoder()
                        agg["product_enc"] = le.fit_transform(agg["product"])
                        X = agg[["product_enc", "month_num"]].values
                        y = agg["quantity"].values
                        rf = RandomForestRegressor(n_estimators=200, random_state=42)
                        rf.fit(X, y)
                        r2 = rf.score(X, y)
                        next_month = (datetime.now().month % 12) + 1
                        predictions = []
                        for i, prod in enumerate(le.classes_):
                            pred = rf.predict([[i, next_month]])[0]
                            predictions.append({"Product": prod, "Predicted Qty": max(0, round(pred, 1))})
                        pred_df = pd.DataFrame(predictions).sort_values("Predicted Qty", ascending=False)
                        st.success("AI Analysis Complete!")
                        st.dataframe(pred_df, use_container_width=True)
                        most_pred = pred_df.iloc[0]
                        least_pred = pred_df.iloc[-1]
                        st.markdown('<div style="padding:1rem; background:#a5d6a7; border-radius:8px; margin:10px 0; color:#2e7d32; font-weight:700; font-size:1.05rem;">Most Purchased Next Month (Predicted): <b>' + most_pred["Product"] + '</b> (' + str(most_pred["Predicted Qty"]) + ' units)</div>', unsafe_allow_html=True)
                        st.markdown('<div style="padding:1rem; background:#ef9a9a; border-radius:8px; margin:10px 0; color:#c62828; font-weight:700; font-size:1.05rem;">Least Purchased Next Month (Predicted): <b>' + least_pred["Product"] + '</b> (' + str(least_pred["Predicted Qty"]) + ' units)</div>', unsafe_allow_html=True)
                        st.caption("Model R2 Score: " + str(round(r2, 3)) + " (1.0 = perfect prediction)")

    # ==================================================================
    # MENU: MANAGER DASHBOARD (Manager only)
    # ==================================================================
    elif menu == "Manager Dashboard" and role == "manager":
        show_manager_dashboard()

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.caption("Mobile-friendly Store Tracker v3.3")

# ------------------------------------------------------------------
# 7. ROUTING
# ------------------------------------------------------------------
if not st.session_state.logged_in:
    if st.session_state.auth_page == "login":
        show_login_page()
    elif st.session_state.auth_page == "register":
        show_register_page()
    elif st.session_state.auth_page == "register_manager":
        show_manager_register_page()
else:
    show_main_app()
