import streamlit as st
import pandas as pd
import requests
from io import StringIO
import hmac

# ==============================
# CONFIG
# ==============================
st.set_page_config(
    page_title="NLO1 Dashboard",
    layout="wide"
)

# ==============================
# LOGIN
# ==============================
def check_password():
    def login_form():
        st.title("🚗 NLO1 Dashboard")
        with st.form("login"):
            st.text_input("Password", type="password", key="password")
            if st.form_submit_button("Masuk"):
                if hmac.compare_digest(
                    st.session_state.password,
                    st.secrets.get("password", "nlo1dashboard")
                ):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Password salah")

    if not st.session_state.get("authenticated", False):
        login_form()
        st.stop()

check_password()

# ==============================
# LOAD DATA (ANTI ERROR VERSION)
# ==============================
@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1WyUxyGQBD9SJQNSQ7WK_KIKVLiU8EbG6e9cqiQMmI1g/export?format=csv"
    
    try:
        res = requests.get(url)
        data = StringIO(res.text)
        df = pd.read_csv(data, sep=None, engine="python")
        
        # bersihin header
        df.columns = df.columns.str.strip()
        
        return df
    except Exception as e:
        st.error(f"Gagal load data: {e}")
        return pd.DataFrame()

df = load_data()

# ==============================
# VALIDATION
# ==============================
if df.empty:
    st.warning("⚠️ Data kosong atau gagal load")
    st.stop()

# ==============================
# CLEAN DATA
# ==============================
# convert date
if "PDIcomp. Date" in df.columns:
    df["PDIcomp. Date"] = pd.to_datetime(df["PDIcomp. Date"], errors="coerce")

# convert numeric
if "L/Time Total" in df.columns:
    df["L/Time Total"] = pd.to_numeric(df["L/Time Total"], errors="coerce")

# ==============================
# TITLE
# ==============================
st.title("📊 NLO1 Production Dashboard")

# ==============================
# KPI
# ==============================
col1, col2, col3 = st.columns(3)

col1.metric("Total Unit", len(df))

col2.metric(
    "Avg Lead Time",
    round(df["L/Time Total"].mean(), 2) if "L/Time Total" in df else "-"
)

col3.metric(
    "Max Lead Time",
    round(df["L/Time Total"].max(), 2) if "L/Time Total" in df else "-"
)

st.divider()

# ==============================
# FILTER
# ==============================
if "Dealer" in df.columns:
    dealer = st.selectbox(
        "Filter Dealer",
        ["All"] + list(df["Dealer"].dropna().unique())
    )

    if dealer != "All":
        df = df[df["Dealer"] == dealer]

# ==============================
# TABLE
# ==============================
st.subheader("Data Table")
st.dataframe(df, use_container_width=True)

# ==============================
# CHART
# ==============================
if "L/Time Total" in df.columns:
    st.subheader("Lead Time Trend")
    st.line_chart(df["L/Time Total"])

# ==============================
# FOOTER
# ==============================
st.caption("Auto update dari Google Sheets • Refresh tiap 60 detik")
