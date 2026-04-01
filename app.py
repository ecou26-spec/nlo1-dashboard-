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
# LOAD DATA (ANTI ERROR TOTAL)
# ==============================
@st.cache_data(ttl=30)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1WyUxyGQBD9SJQNSQ7WK_KIKVLiU8EbG6e9cqiQMmI1g/export?format=csv"
    
    try:
        res = requests.get(url)
        data = StringIO(res.text)

        df = pd.read_csv(
            data,
            sep=",",
            encoding="utf-8",
            on_bad_lines="skip"
        )

        # ==============================
        # CLEAN HEADER
        # ==============================
        df.columns = df.columns.str.strip()
        df.columns = df.columns.str.replace(" ", "_")
        df.columns = df.columns.str.replace("/", "_")

        # buang baris kosong
        df = df.dropna(how="all")

        return df

    except Exception as e:
        st.error(f"Gagal load data: {e}")
        return pd.DataFrame()

df = load_data()

# ==============================
# VALIDASI
# ==============================
if df.empty:
    st.warning("⚠️ Data kosong atau gagal load")
    st.stop()

# ==============================
# DEBUG (optional, bisa dihapus nanti)
# ==============================
st.write("Kolom terbaca:", df.columns)

# ==============================
# CLEAN DATA TYPE
# ==============================
# convert datetime
date_cols = [
    "PDIcomp._Date",
    "PPOin_Date",
    "PPOcomp._Date",
    "SPUin_Date",
    "SPUcomp_ActualDateTime"
]

for col in date_cols:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

# convert numeric
if "L_Time_Total" in df.columns:
    df["L_Time_Total"] = pd.to_numeric(df["L_Time_Total"], errors="coerce")

# ==============================
# TITLE
# ==============================
st.title("📊 NLO1 Production Dashboard")

# ==============================
# KPI (AMAN)
# ==============================
col1, col2, col3 = st.columns(3)

col1.metric("Total Unit", len(df))

if "L_Time_Total" in df.columns:
    col2.metric("Avg Lead Time", round(df["L_Time_Total"].mean(), 2))
    col3.metric("Max Lead Time", round(df["L_Time_Total"].max(), 2))
else:
    col2.metric("Avg Lead Time", "-")
    col3.metric("Max Lead Time", "-")

st.divider()

# ==============================
# FILTER
# ==============================
if "Dealer" in df.columns:
    dealer = st.selectbox(
        "Filter Dealer",
        ["All"] + sorted(df["Dealer"].dropna().unique())
    )

    if dealer != "All":
        df = df[df["Dealer"] == dealer]

# ==============================
# TABLE
# ==============================
st.subheader("📋 Data Table")
st.dataframe(df, use_container_width=True)

# ==============================
# CHART
# ==============================
if "L_Time_Total" in df.columns:
    st.subheader("📈 Lead Time Trend")
    st.line_chart(df["L_Time_Total"])

# ==============================
# FOOTER
# ==============================
st.caption("Auto update dari Google Sheets • Refresh tiap 30 detik")
