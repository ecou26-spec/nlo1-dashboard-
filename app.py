import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
import hmac
import json
from datetime import datetime

# ==============================
# CONFIG
# ==============================
st.set_page_config(
    page_title="NLO1 Lead Time Dashboard",
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
# FIELD MAPPING (TIDAK DIUBAH)
# ==============================
FIELDS = {
    "Receiving": "L/T PDI-PPOin",
    "PPO":       "L/T PPOIn-PPOcomp",
    "SPU In":    "L/T PPO_SPUin",
    "SPU Comp":  "L/T SPUin_SPUcomp",
    "Total":     "L/Time Total",
}

# ==============================
# LOAD DATA (FIX TOTAL)
# ==============================
@st.cache_data(ttl=60)
def load_from_sheets():
    try:
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_url(st.secrets["sheet_url"])
        ws = sh.get_worksheet(0)
        data = ws.get_all_records()

        df = pd.DataFrame(data)

        # ==============================
        # CLEAN HEADER (SUPER PENTING)
        # ==============================
        df.columns = (
            df.columns
            .str.strip()
            .str.replace('\ufeff', '', regex=False)
        )

        # NORMALISASI HEADER YANG SERING ERROR
        df.rename(columns={
            "L/T SPUin _SPUcomp": "L/T SPUin_SPUcomp",
            "L/T SPUin  _SPUcomp": "L/T SPUin_SPUcomp",
            "L/T SPUin_SPUcomp ": "L/T SPUin_SPUcomp",
            "L/Time Total ": "L/Time Total",
        }, inplace=True)

        return df

    except Exception as e:
        st.error(f"Gagal load data: {e}")
        return pd.DataFrame()

df = load_from_sheets()

if df.empty:
    st.warning("Data kosong")
    st.stop()

# ==============================
# PREPARE DATA
# ==============================
def get_loc(model):
    m = str(model).upper()
    if "LEXUS" in m: return "NVDC Sunter Lexus"
    if "RUSH" in m: return "NVDC Sunter"
    return "NVDC Cibitung"

def prepare_df(df):
    # VALIDASI KOLOM WAJIB
    required = ["Model", "PDIcomp. Date", "L/Time Total"]

    for col in required:
        if col not in df.columns:
            st.error(f"Kolom tidak ditemukan: {col}")
            st.write("Kolom tersedia:", df.columns)
            st.stop()

    # DATE
    df["_date"] = pd.to_datetime(
        df["PDIcomp. Date"],
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    df["_month"] = df["_date"].str[:7]

    # LOCATION
    df["_loc"] = df["Model"].apply(get_loc)

    return df.dropna(subset=["_date"])

df = prepare_df(df)

# ==============================
# CONVERT NUMERIC (ANTI ERROR)
# ==============================
for col in FIELDS.values():
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ==============================
# SIMPLE KPI TEST
# ==============================
st.title("📊 NLO1 Dashboard")

col1, col2, col3 = st.columns(3)

col1.metric("Total Unit", len(df))

if "L/Time Total" in df.columns:
    col2.metric("Avg Lead Time", round(df["L/Time Total"].mean(), 2))
    col3.metric("Max Lead Time", round(df["L/Time Total"].max(), 2))
else:
    col2.metric("Avg Lead Time", "-")
    col3.metric("Max Lead Time", "-")

# ==============================
# TABLE
# ==============================
st.dataframe(df, use_container_width=True)

# ==============================
# CHART
# ==============================
if "L/Time Total" in df.columns:
    st.line_chart(df["L/Time Total"])
