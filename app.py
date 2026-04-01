import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import hmac

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
                    if hmac.compare_digest(st.session_state.password, st.secrets.get("password", "nlo1dashboard")):
                        st.session_state.authenticated = True
                        st.rerun()
                    else:
                        st.error("Password salah")

    if not st.session_state.get("authenticated", False):
        login_form()
        st.stop()

check_password()

# ── PARAMS ────────────────────────────────────────────────────────────────────
PARAMS = {
    "ALL": {
        "Receiving":  {"avg": 1.54,  "std": 1.143},
        "PPO":        {"avg": 2.86,  "std": 2.135},
        "SPU In":     {"avg": 1.01,  "std": 0.523},
        "SPU Comp":   {"avg": 0.80,  "std": 0.479},
        "Total":      {"avg": 6.26,  "std": 2.468},
    },
    "NVDC Cibitung": {
        "Receiving":  {"avg": 0.974, "std": 0.416},
        "PPO":        {"avg": 2.934, "std": 2.317},
        "SPU In":     {"avg": 1.171, "std": 0.409},
        "SPU Comp":   {"avg": 0.934, "std": 0.424},
        "Total":      {"avg": 6.079, "std": 2.806},
    },
    "NVDC Sunter": {
        "Receiving":  {"avg": 4.0,   "std": 0.5},
        "PPO":        {"avg": 1.25,  "std": 0.5},
        "SPU In":     {"avg": 1.0,   "std": 0.0},
        "SPU Comp":   {"avg": 0.75,  "std": 0.0},
        "Total":      {"avg": 7.0,   "std": 0.5},
    },
    "NVDC Sunter Lexus": {
        "Receiving":  {"avg": 2.667, "std": 0.289},
        "PPO":        {"avg": 4.0,   "std": 0.5},
        "SPU In":     {"avg": 0.0,   "std": 0.0},
        "SPU Comp":   {"avg": 0.0,   "std": 0.0},
        "Total":      {"avg": 6.667, "std": 0.764},
    },
}

FIELDS = {
    "Receiving": "L/T PDI-PPOin",
    "PPO":       "L/T PPOIn-PPOcomp",
    "SPU In":    "L/T PPO_SPUin",
    "SPU Comp":  "L/T SPUin _SPUcomp",
    "Total":     "L/Time Total",
}

PROC_COLORS = {
    "Receiving": "#3d9bff",
    "PPO":       "#a066ff",
    "SPU In":    "#22d3ee",
    "SPU Comp":  "#ffcc40",
    "Total":     "#ff4060",
}

LOC_MAP = {
    "ALL":               ["ALPHARD","CAMRY","HIACE","HILUX","LANDCRUISER","RUSH","VELLFIRE","VOXY","LEXUS"],
    "NVDC Cibitung":     ["ALPHARD","CAMRY","HIACE","HILUX","LANDCRUISER","VELLFIRE","VOXY"],
    "NVDC Sunter":       ["RUSH"],
    "NVDC Sunter Lexus": ["LEXUS"],
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def get_loc(model):
    m = str(model).upper()
    if "LEXUS" in m: return "NVDC Sunter Lexus"
    if "RUSH"  in m: return "NVDC Sunter"
    return "NVDC Cibitung"

def to_mins(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return None
    return round(v * 60)

def fmt_mins(v):
    m = to_mins(v)
    return f"{m} min" if m is not None else "—"

def ach_color(a):
    if a is None: return "#888"
    if a >= 95:   return "#00e5a0"
    if a >= 90:   return "#ffcc40"
    return "#ff4060"

def classify(val, avg, std):
    if pd.isna(val) or val is None: return None
    lo, hi = avg - std, avg + std
    if val <= lo: return "FAST"
    if val <= hi: return "NORMAL"
    return "NG"

# ── COMPUTE ───────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def compute(df_raw: bytes):
    df = pd.read_csv(pd.io.common.BytesIO(df_raw), sep=None, engine="python", encoding="utf-8-sig")
    df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)

    # Parse date
    df["_date"] = pd.to_datetime(df["PDIcomp. Date"], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
    df["_month"] = df["_date"].str[:7]
    df["_loc"] = df["Model"].apply(get_loc)
    df = df.dropna(subset=["_date"])

    return df

def calc_stats(df, loc):
    if df.empty: return None
    params = PARAMS[loc]
    result = {}

    for pname, col in FIELDS.items():
        if col not in df.columns:
            result[pname] = None
            continue
        p = params[pname]
        vals = pd.to_numeric(df[col], errors="coerce")
        valid = vals.dropna()
        if valid.empty:
            result[pname] = None
            continue
        statuses = vals.apply(lambda v: classify(v, p["avg"], p["std"]))
        fast   = (statuses == "FAST").sum()
        normal = (statuses == "NORMAL").sum()
        ng     = (statuses == "NG").sum()
        na     = statuses.isna().sum()
        tc     = fast + normal + ng
        result[pname] = {
            "fast": int(fast), "normal": int(normal), "ng": int(ng), "na": int(na),
            "total_classified": int(tc),
            "pct_fast":   round(fast/tc*100, 1) if tc else 0,
            "pct_normal": round(normal/tc*100, 1) if tc else 0,
            "pct_ng":     round(ng/tc*100, 1) if tc else 0,
            "achieved":   round((fast+normal)/tc*100, 1) if tc else None,
            "actual_avg": round(valid.mean(), 3),
            "actual_std": round(valid.std(), 3) if len(valid) > 1 else 0,
            "param_avg":  p["avg"],
            "param_std":  p["std"],
            "thresh_lo":  round(p["avg"] - p["std"], 3),
            "thresh_hi":  round(p["avg"] + p["std"], 3),
        }

    # Models
    models = []
    for m, mdf in df.groupby("Model"):
        p = params["Total"]
        col = FIELDS["Total"]
        tv = pd.to_numeric(mdf[col], errors="coerce") if col in mdf.columns else pd.Series(dtype=float)
        sts = tv.apply(lambda v: classify(v, p["avg"], p["std"]))
        tc2 = (sts.notna()).sum()
        fast2 = (sts == "FAST").sum()
        norm2 = (sts == "NORMAL").sum()
        ng2   = (sts == "NG").sum()
        ppo_col = FIELDS["PPO"]
        recv_col = FIELDS["Receiving"]
        models.append({
            "name": m, "n": len(mdf),
            "total": round(tv.mean(), 3) if not tv.dropna().empty else None,
            "ppo":   round(pd.to_numeric(mdf[ppo_col], errors="coerce").mean(), 3) if ppo_col in mdf.columns else None,
            "recv":  round(pd.to_numeric(mdf[recv_col], errors="coerce").mean(), 3) if recv_col in mdf.columns else None,
            "fast": int(fast2), "normal": int(norm2), "ng": int(ng2),
            "achieved": round((fast2+norm2)/tc2*100, 1) if tc2 else None,
        })
    models.sort(key=lambda x: x["total"] if x["total"] is not None else 999)

    t = result.get("Total")
    return {
        "total_units":   len(df),
        "models_count":  df["Model"].nunique(),
        "ng_units":      t["ng"] if t else 0,
        "processes":     result,
        "models":        models,
    }

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0a0f1e; color: #e0e8ff; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding: 1rem 2rem; max-width: 1400px; }
.kpi-box {
    background: linear-gradient(135deg,#0d1526,#111d35);
    border: 1px solid rgba(100,160,255,.15);
    border-radius: 12px; padding: 16px 20px; text-align: center;
}
.kpi-n { font-size: 2rem; font-weight: 800; font-family: monospace; }
.kpi-l { font-size: .7rem; color: #7a90bb; text-transform: uppercase; letter-spacing: .08em; margin-top: 2px; }
.proc-card {
    background: #0d1526;
    border: 1px solid rgba(100,160,255,.12);
    border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
}
.proc-title { font-size: .75rem; font-weight: 700; letter-spacing: .06em; margin-bottom: 8px; }
.stat-row { display: flex; justify-content: space-between; margin-bottom: 4px; }
.stat-l { font-size: .6rem; color: #7a90bb; text-transform: uppercase; }
.stat-v { font-size: .65rem; font-weight: 600; font-family: monospace; }
.finding-card {
    background: #0d1526; border-radius: 10px;
    border: 1px solid rgba(100,160,255,.1);
    padding: 12px 16px; margin-bottom: 8px;
}
.ach-bar-wrap { background: #111d35; border-radius: 8px; height: 28px; overflow: hidden; margin: 8px 0; position: relative; }
.ach-bar-inner { height: 100%; border-radius: 8px; transition: width .5s; display: flex; align-items: center; padding-left: 10px; }
.section-title { font-size: .8rem; font-weight: 700; color: #7fb3ff; text-transform: uppercase;
    letter-spacing: .08em; margin: 20px 0 10px 0; border-bottom: 1px solid rgba(100,160,255,.15); padding-bottom: 6px; }
div[data-testid="stMetric"] { background: #0d1526; border-radius: 10px; padding: 12px; border: 1px solid rgba(100,160,255,.12); }
</style>
""", unsafe_allow_html=True)

# ── SIDEBAR — Upload & Info ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📂 Update Data")
    uploaded = st.file_uploader("Upload CSV", type=["csv"], label_visibility="collapsed")
    if uploaded:
        st.session_state["csv_data"] = uploaded.read()
        st.session_state["csv_name"] = uploaded.name
        st.success(f"✅ {uploaded.name}")

    if "csv_name" in st.session_state:
        st.caption(f"File aktif: `{st.session_state['csv_name']}`")

    st.markdown("---")
    st.markdown("### ℹ️ Info")
    st.caption("NLO1 Dept · Lead Time Std Dev Dashboard · Mar 2026")
    st.caption("📐 Parameter per lokasi (Cibitung / Sunter / Lexus)")

    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
if "csv_data" not in st.session_state:
    st.markdown("""
    <div style='text-align:center; padding: 80px 0; color: #7a90bb'>
        <div style='font-size:3rem'>📂</div>
        <h3>Upload CSV untuk mulai</h3>
        <p>Gunakan panel kiri untuk upload file<br>
        <code>Detail_Process_Vehicle_by_Process_Production.csv</code></p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df = compute(st.session_state["csv_data"])

# ── FILTERS ───────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🔽 Filter</div>', unsafe_allow_html=True)

col_loc, col_mon, col_day = st.columns([2, 2, 4])

with col_loc:
    loc_opts = ["ALL", "NVDC Cibitung", "NVDC Sunter", "NVDC Sunter Lexus"]
    loc_labels = {"ALL": "All", "NVDC Cibitung": "Cibitung", "NVDC Sunter": "Sunter", "NVDC Sunter Lexus": "Lexus"}
    sel_loc = st.radio("Lokasi", loc_opts, format_func=lambda x: loc_labels[x], horizontal=True, label_visibility="collapsed")

with col_mon:
    months = sorted(df["_month"].dropna().unique().tolist())
    month_labels = {m: datetime.strptime(m, "%Y-%m").strftime("%b '%y") for m in months}
    sel_month = st.radio("Bulan", months, format_func=lambda x: month_labels[x],
                         index=len(months)-1, horizontal=True, label_visibility="collapsed")

with col_day:
    dates_in_month = sorted(df[df["_month"] == sel_month]["_date"].dropna().unique().tolist())
    day_opts = ["ALL"] + dates_in_month
    def day_label(d):
        if d == "ALL": return "📅 All"
        dt = datetime.strptime(d, "%Y-%m-%d")
        days = ["Su","Mo","Tu","We","Th","Fr","Sa"]
        return f"{dt.day} {days[dt.weekday()]}"
    sel_date = st.radio("Tanggal", day_opts, format_func=day_label, horizontal=True, label_visibility="collapsed")

# ── FILTER DATA ───────────────────────────────────────────────────────────────
df_loc = df if sel_loc == "ALL" else df[df["_loc"] == sel_loc]
if sel_date == "ALL":
    df_filt = df_loc[df_loc["_month"] == sel_month]
else:
    df_filt = df_loc[df_loc["_date"] == sel_date]

stats = calc_stats(df_filt, sel_loc)

if not stats:
    st.warning("Tidak ada data untuk filter ini.")
    st.stop()

# ── PARAM NOTE ────────────────────────────────────────────────────────────────
param_desc = {
    "ALL": "Global (25 models avg)",
    "NVDC Cibitung": "Cibitung-specific (ALPHARD/CAMRY/HIACE/HILUX/LANDCRUISER/VELLFIRE/VOXY)",
    "NVDC Sunter": "Sunter-specific (RUSH)",
    "NVDC Sunter Lexus": "Sunter Lexus-specific (LEXUS)",
}
date_label = sel_date if sel_date != "ALL" else month_labels.get(sel_month, sel_month)
st.caption(f"📐 Param: {param_desc[sel_loc]} | 📅 {date_label}")

# ── KPI CARDS ─────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
t_proc = stats["processes"].get("Total")
ach = t_proc["achieved"] if t_proc else None

with c1:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#7fb3ff">{stats['total_units']:,}</div>
        <div class="kpi-l">Total Units</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#00e5a0">{stats['models_count']}</div>
        <div class="kpi-l">Models</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#ff4060">{stats['ng_units']}</div>
        <div class="kpi-l">Over L/T</div>
    </div>""", unsafe_allow_html=True)

# ── OVERALL ACHIEVEMENT ───────────────────────────────────────────────────────
st.markdown('<div class="section-title">📊 Overall L/T Achievement</div>', unsafe_allow_html=True)

if t_proc:
    ach_val = ach or 0
    color = ach_color(ach)
    fast_pct  = t_proc["pct_fast"]
    norm_pct  = t_proc["pct_normal"]
    ng_pct    = t_proc["pct_ng"]
    thresh_lo = t_proc["thresh_lo"]
    thresh_hi = t_proc["thresh_hi"]

    st.markdown(f"""
    <div style='background:#111d35; border-radius:10px; padding:16px 20px; border:1px solid rgba(100,160,255,.15)'>
        <div style='display:flex; justify-content:space-between; margin-bottom:8px'>
            <span style='font-size:2.2rem; font-weight:800; color:{color}'>{ach_val:.1f}%</span>
            <span style='color:#7a90bb; font-size:.7rem; align-self:center'>
                FAST ≤{to_mins(thresh_lo)} min · NORMAL {to_mins(thresh_lo)}–{to_mins(thresh_hi)} min · Over >{to_mins(thresh_hi)} min
            </span>
        </div>
        <div style='display:flex; height:24px; border-radius:6px; overflow:hidden; gap:2px'>
            <div style='width:{fast_pct}%; background:#00e5a0; display:flex; align-items:center; justify-content:center;
                font-size:.55rem; font-weight:700; color:#0a0f1e'>{fast_pct:.0f}%</div>
            <div style='width:{norm_pct}%; background:#3d9bff; display:flex; align-items:center; justify-content:center;
                font-size:.55rem; font-weight:700; color:#0a0f1e'>{norm_pct:.0f}%</div>
            <div style='width:{ng_pct}%; background:#ff4060; display:flex; align-items:center; justify-content:center;
                font-size:.55rem; font-weight:700; color:#fff'>{ng_pct:.0f}%</div>
        </div>
        <div style='display:flex; gap:16px; margin-top:8px; font-size:.6rem; color:#7a90bb'>
            <span>🟢 FAST: {t_proc["fast"]} units</span>
            <span>🔵 NORMAL: {t_proc["normal"]} units</span>
            <span>🔴 Over L/T: {t_proc["ng"]} units</span>
            <span>avg {fmt_mins(t_proc["actual_avg"])}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── PROCESS CARDS ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">⚙️ Per Process</div>', unsafe_allow_html=True)

proc_cols = st.columns(5)
for i, (pname, color) in enumerate(PROC_COLORS.items()):
    p = stats["processes"].get(pname)
    with proc_cols[i]:
        if not p:
            st.markdown(f"""<div class="proc-card" style="border-color:{color}40">
                <div class="proc-title" style="color:{color}">{pname}</div>
                <div style="color:#555; font-size:.6rem">N/A</div>
            </div>""", unsafe_allow_html=True)
            continue
        ach_p = p["achieved"] or 0
        st.markdown(f"""<div class="proc-card" style="border-color:{color}50">
            <div class="proc-title" style="color:{color}">{pname}</div>
            <div style="font-size:1.4rem; font-weight:800; color:{ach_color(p['achieved'])};
                font-family:monospace; margin-bottom:6px">{ach_p:.1f}%</div>
            <div class="stat-row">
                <span class="stat-l">Actual Avg</span>
                <span class="stat-v" style="color:{color}">{fmt_mins(p['actual_avg'])}</span>
            </div>
            <div class="stat-row">
                <span class="stat-l">Param Avg</span>
                <span class="stat-v" style="color:#7a90bb">{fmt_mins(p['param_avg'])}</span>
            </div>
            <div class="stat-row">
                <span class="stat-l">Actual Std</span>
                <span class="stat-v" style="color:{color}">±{to_mins(p['actual_std'])} min</span>
            </div>
            <div class="stat-row">
                <span class="stat-l">Param Std</span>
                <span class="stat-v" style="color:#7a90bb">±{to_mins(p['param_std'])} min</span>
            </div>
            <div style="margin-top:8px; font-size:.55rem; display:flex; justify-content:space-between; color:#7a90bb">
                <span style="color:#00e5a0">≤{to_mins(p['thresh_lo'])}</span>
                <span>min</span>
                <span style="color:#ff4060">&gt;{to_mins(p['thresh_hi'])}</span>
            </div>
            <div style="display:flex; height:6px; border-radius:3px; overflow:hidden; margin-top:4px; gap:1px">
                <div style="width:{p['pct_fast']}%; background:#00e5a0"></div>
                <div style="width:{p['pct_normal']}%; background:#3d9bff"></div>
                <div style="width:{p['pct_ng']}%; background:#ff4060"></div>
            </div>
        </div>""", unsafe_allow_html=True)

# ── BOTTOM SECTION ────────────────────────────────────────────────────────────
left_col, right_col = st.columns([3, 2])

with left_col:
    st.markdown('<div class="section-title">🚗 Model Summary</div>', unsafe_allow_html=True)
    if stats["models"]:
        model_df = pd.DataFrame(stats["models"])
        model_df["Avg L/T"] = model_df["total"].apply(fmt_mins)
        model_df["Avg PPO"] = model_df["ppo"].apply(fmt_mins)
        model_df["Avg Recv"] = model_df["recv"].apply(fmt_mins)
        model_df["Achievement"] = model_df["achieved"].apply(lambda x: f"{x:.1f}%" if x is not None else "—")
        model_df["Over L/T"] = model_df["ng"]
        disp = model_df[["name","n","Achievement","Over L/T","Avg L/T","Avg PPO","Avg Recv"]].rename(
            columns={"name":"Model","n":"Units"})
        st.dataframe(disp, use_container_width=True, hide_index=True,
            column_config={
                "Achievement": st.column_config.TextColumn("Achievement"),
                "Over L/T": st.column_config.NumberColumn("Over L/T"),
            })

    # Daily table (only when ALL dates selected)
    if sel_date == "ALL":
        st.markdown('<div class="section-title">📅 Daily Achievement</div>', unsafe_allow_html=True)
        daily_rows = []
        for d in dates_in_month:
            d_df = df_loc[df_loc["_date"] == d]
            if d_df.empty: continue
            d_stats = calc_stats(d_df, sel_loc)
            if not d_stats: continue
            t = d_stats["processes"].get("Total")
            dt = datetime.strptime(d, "%Y-%m-%d")
            days_id = ["Min","Sen","Sel","Rab","Kam","Jum","Sab"]
            daily_rows.append({
                "Tanggal": f"{dt.day} {days_id[dt.weekday()]}",
                "Units": d_stats["total_units"],
                "Over L/T": d_stats["ng_units"],
                "Achievement": f"{t['achieved']:.1f}%" if t and t["achieved"] is not None else "—",
                "Avg L/T": fmt_mins(t["actual_avg"]) if t else "—",
            })
        if daily_rows:
            st.dataframe(pd.DataFrame(daily_rows), use_container_width=True, hide_index=True)

with right_col:
    st.markdown('<div class="section-title">💡 Key Findings</div>', unsafe_allow_html=True)

    findings = []

    # Best process
    best_p, best_name = None, None
    for pn, p in stats["processes"].items():
        if p and p["achieved"] is not None:
            if best_p is None or p["achieved"] > best_p["achieved"]:
                best_p, best_name = p, pn
    if best_p and best_p["achieved"] >= 95:
        findings.append({
            "ico": "🟢", "title": f"{best_name} — Proses Terbaik",
            "desc": f"Achievement {best_p['achieved']}% — sangat baik. Avg {fmt_mins(best_p['actual_avg'])} (param {fmt_mins(best_p['param_avg'])}). Jadikan benchmark.",
            "color": "#00e5a0"
        })

    # Worst process
    worst_p, worst_name = None, None
    for pn, p in stats["processes"].items():
        if p and p["achieved"] is not None:
            if worst_p is None or p["achieved"] < worst_p["achieved"]:
                worst_p, worst_name = p, pn
    if worst_p and worst_p["achieved"] is not None and worst_p["achieved"] < 90:
        findings.append({
            "ico": "🔴", "title": f"{worst_name} — Perlu Perhatian",
            "desc": f"Achievement {worst_p['achieved']}% di bawah target. Avg {fmt_mins(worst_p['actual_avg'])} vs param {fmt_mins(worst_p['param_avg'])}.",
            "color": "#ff4060"
        })

    # Worst model
    if stats["models"]:
        ng_models = [m for m in stats["models"] if m["ng"] and m["ng"] > 0]
        if ng_models:
            top = max(ng_models, key=lambda x: x["ng"])
            findings.append({
                "ico": "🚗", "title": f"{top['name']} — Model Paling Bermasalah",
                "desc": f"{top['ng']} Over L/T dari {top['n']} units (ach. {top['achieved']}%). Avg L/T {fmt_mins(top['total'])}, avg PPO {fmt_mins(top['ppo'])}.",
                "color": "#ff4060"
            })

    # High std dev
    high_std, high_name = None, None
    for pn, p in stats["processes"].items():
        if p and p["actual_std"] and p["param_std"] and p["param_std"] > 0:
            ratio = p["actual_std"] / p["param_std"]
            if ratio > 1.5:
                if high_std is None or ratio > high_std:
                    high_std = ratio
                    high_name = pn
                    high_p = p
    if high_name:
        findings.append({
            "ico": "📈", "title": f"{high_name} — Variabilitas Tinggi",
            "desc": f"Std dev ±{to_mins(high_p['actual_std'])} min ({round((high_std-1)*100)}% di atas param ±{to_mins(high_p['param_std'])} min). Konsistensi proses perlu perbaikan.",
            "color": "#22d3ee"
        })

    if not findings:
        findings.append({
            "ico": "✅", "title": "Semua Proses Normal",
            "desc": f"Achievement overall {ach:.1f}%. Tidak ada anomali signifikan pada periode ini.",
            "color": "#00e5a0"
        })

    for f in findings:
        st.markdown(f"""<div class="finding-card" style="border-left: 3px solid {f['color']}">
            <div style="font-size:.7rem; font-weight:700; color:{f['color']}; margin-bottom:4px">
                {f['ico']} {f['title']}
            </div>
            <div style="font-size:.62rem; color:#a0b4cc; line-height:1.5">{f['desc']}</div>
        </div>""", unsafe_allow_html=True)
