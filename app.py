import streamlit as st
import pandas as pd
import numpy as np
import hmac
from datetime import datetime

st.set_page_config(
    page_title="NLO1 Lead Time Dashboard",
    page_icon="🚗",
    layout="wide"
)

# 🔐 LOGIN
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

# 📡 LOAD DATA (CSV MODE)
@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/1WyUxyGQBD9SJQNSQ7WK_KIKVLiU8EbG6e9cqiQMmI1g/export?format=csv"
    return pd.read_csv(url)

df = load_data()

# 🧹 CLEAN DATA
df.columns = df.columns.str.strip()

# convert date
df["PDIcomp. Date"] = pd.to_datetime(df["PDIcomp. Date"], errors="coerce")

# KPI
st.title("📊 NLO1 Production Dashboard")

col1, col2, col3 = st.columns(3)
col1.metric("Total Unit", len(df))
col2.metric("Avg Lead Time", round(df["L/Time Total"].mean(), 2))
col3.metric("Max Lead Time", round(df["L/Time Total"].max(), 2))

st.divider()

# FILTER
dealer = st.selectbox("Dealer", ["All"] + list(df["Dealer"].dropna().unique()))

if dealer != "All":
    df = df[df["Dealer"] == dealer]

# TABLE
st.dataframe(df, use_container_width=True)

# CHART
st.subheader("Lead Time Trend")
st.line_chart(df["L/Time Total"])
