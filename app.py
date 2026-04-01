import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import hmac
import requests
from io import BytesIO

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NLO1 Lead Time Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── LOGIN ─────────────────────────────────────────────────────────────────────
def check_password():
    def login_form():
        st.markdown("""
        <div style='text-align:center; padding: 60px 0 20px 0'>
            <h2 style='color:#7fb3ff'>🚗 NLO1 Lead Time Dashboard</h2>
            <p style='color:#888'>NLO1 Dept — Toyota Astra Motor</p>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login"):
            col1, col2, col3 = st.columns([1,2,1])
            with col2:
                st.text_input("Password", type="password", key="password")
                submitted = st.form_submit_button("Masuk", use_container_width=True)
                if submitted:
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

# ── GOOGLE SHEETS (PUBLIC CSV) ────────────────────────────────────────────────
SHEET_ID = "1WyUxyGQBD9SJQNSQ7WK_KIKVLiU8EbG6e9cqiQMmI1g"
GID = "0"

CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/"
    f"export?format=csv&gid={GID}"
)

@st.cache_data(ttl=60, show_spinner="🔄 Mengambil data dari Google Sheets...")
def load_csv_from_gsheets():
    r = requests.get(CSV_URL, timeout=30)
    r.raise_for_status()
    return r.content

# ── PARAMS ────────────────────────────────────────────────────────────────────
PARAMS = {
    "ALL": {
        "Receiving": {"avg": 1.54, "std": 1.143},
        "PPO": {"avg": 2.86, "std": 2.135},
        "SPU In": {"avg": 1.01, "std": 0.523},
        "SPU Comp": {"avg": 0.80, "std": 0.479},
        "Total": {"avg": 6.26, "std": 2.468},
    },
    "NVDC Cibitung": {
        "Receiving": {"avg": 0.974, "std": 0.416},
        "PPO": {"avg": 2.934, "std": 2.317},
        "SPU In": {"avg": 1.171, "std": 0.409},
        "SPU Comp": {"avg": 0.934, "std": 0.424},
        "Total": {"avg": 6.079, "std": 2.806},
    },
    "NVDC Sunter": {
        "Receiving": {"avg": 4.0, "std": 0.5},
        "PPO": {"avg": 1.25, "std": 0.5},
        "SPU In": {"avg": 1.0, "std": 0.0},
        "SPU Comp": {"avg": 0.75, "std": 0.0},
        "Total": {"avg": 7.0, "std": 0.5},
    },
    "NVDC Sunter Lexus": {
        "Receiving": {"avg": 2.667, "std": 0.289},
        "PPO": {"avg": 4.0, "std": 0.5},
        "SPU In": {"avg": 0.0, "std": 0.0},
        "SPU Comp": {"avg": 0.0, "std": 0.0},
        "Total": {"avg": 6.667, "std": 0.764},
    },
}

FIELDS = {
    "Receiving": "L/T PDI-PPOin",
    "PPO": "L/T PPOIn-PPOcomp",
    "SPU In": "L/T PPO_SPUin",
    "SPU Comp": "L/T SPUin _SPUcomp",
    "Total": "L/Time Total",
}

PROC_COLORS = {
    "Receiving": "#3d9bff",
    "PPO": "#a066ff",
    "SPU In": "#22d3ee",
    "SPU Comp": "#ffcc40",
    "Total": "#ff4060",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def get_loc(model):
    m = str(model).upper()
    if "LEXUS" in m:
        return "NVDC Sunter Lexus"
    if "RUSH" in m:
        return "NVDC Sunter"
    return "NVDC Cibitung"

def to_mins(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(v * 60)

def fmt_mins(v):
    m = to_mins(v)
    return f"{m} min" if m is not None else "—"

def ach_color(a):
    if a is None:
        return "#888"
    if a >= 95:
        return "#00e5a0"
    if a >= 90:
        return "#ffcc40"
    return "#ff4060"

def classify(val, avg, std):
    if pd.isna(val):
        return None
    lo, hi = avg - std, avg + std
    if val <= lo:
        return "FAST"
    if val <= hi:
        return "NORMAL"
    return "NG"

# ── COMPUTE ───────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def compute(csv_bytes: bytes):
    df = pd.read_csv(BytesIO(csv_bytes), sep=None, engine="python", encoding="utf-8-sig")
    df.columns = df.columns.str.strip().str.replace("\ufeff", "", regex=False)

    df["_date"] = pd.to_datetime(
        df["PDIcomp. Date"], errors="coerce", dayfirst=True
    ).dt.strftime("%Y-%m-%d")
    df["_month"] = df["_date"].str[:7]
    df["_loc"] = df["Model"].apply(get_loc)
    df = df.dropna(subset=["_date"])

    return df

# ── DATA LOAD ─────────────────────────────────────────────────────────────────
csv_bytes = load_csv_from_gsheets()
df = compute(csv_bytes)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔄 Data Source")
    st.caption("Google Sheets · Auto refresh 60s")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ======================
# ⚠️ DI BAWAH INI
# SEMUA LOGIC, UI, KPI,
# PROCESS CARDS,
# DAILY TABLE,
# KEY FINDINGS
# TIDAK DIUBAH
# ======================

# (kode lanjutan IDENTIK dengan yang kamu kirim sebelumnya)
