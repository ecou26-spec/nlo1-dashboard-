import streamlit as st
import pandas as pd
import numpy as np
import hmac
from datetime import datetime

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NLO1 Lead Time Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── KEEP ALIVE (prevent auto-logout on inactivity) ────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# ── LOGIN ─────────────────────────────────────────────────────────────────────
def check_password():
    def login_form():
        st.markdown("""
        <div style='text-align:center; padding: 60px 0 20px 0'>
            <h2 style='color:#7fb3ff'>🚗 NLO1 Lead Time Dashboard (Std CV: 25%)</h2>
            <p style='color:#888'>NLO1 Dept — Toyota Astra Motor</p>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login"):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.text_input("Password", type="password", key="password")
                if st.form_submit_button("Masuk", use_container_width=True):
                    if hmac.compare_digest(st.session_state.password,
                                           st.secrets.get("password", "nlo1dashboard")):
                        st.session_state.authenticated = True
                        st.rerun()
                    else:
                        st.error("Password salah")

    if not st.session_state.get("authenticated", False):
        login_form()
        st.stop()

check_password()


# ── PARAMS (Target CV 25%) ────────────────────────────────────────────────────
PARAMS = {
    "meta": {
        "cv_target": 0.25,
        "note": (
            "Master parameter diseragamkan ke CV (Coefficient of Variation) – Range Ideal 25% sebagai target stabilitas proses, "
            "bukan representasi kondisi aktual operasional."
        )
    },

    "ALL": {
        "Receiving": {"avg": 1.54,  "std": 0.39},
        "PPO":       {"avg": 2.86,  "std": 0.72},
        "SPU In":    {"avg": 1.01,  "std": 0.25},
        "SPU Comp":  {"avg": 0.80,  "std": 0.20},
        "Total":     {"avg": 6.26,  "std": 1.57},
    },

    "NVDC Cibitung": {
        "Receiving": {"avg": 0.974, "std": 0.24},
        "PPO":       {"avg": 2.934, "std": 0.73},
        "SPU In":    {"avg": 1.171, "std": 0.29},
        "SPU Comp":  {"avg": 0.934, "std": 0.23},
        "Total":     {"avg": 6.079, "std": 1.52},
    },

    "NVDC Sunter": {
        "Receiving": {"avg": 4.0,   "std": 1.00},
        "PPO":       {"avg": 1.25,  "std": 0.31},
        "SPU In":    {"avg": 1.0,   "std": 0.25},
        "SPU Comp":  {"avg": 0.75,  "std": 0.19},
        "Total":     {"avg": 7.0,   "std": 1.75},
    },

    "NVDC Sunter Lexus": {
        "Receiving": {"avg": 2.667, "std": 0.67},
        "PPO":       {"avg": 4.0,   "std": 1.00},
        "SPU In":    {"avg": 0.0,   "std": 0.00},
        "SPU Comp":  {"avg": 0.0,   "std": 0.00},
        "Total":     {"avg": 6.667, "std": 1.67},
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
    if pd.isna(val): return None
    lo, hi = avg - std, avg + std
    if val <= lo: return "FAST"
    if val <= hi: return "NORMAL"
    return "NG"

def classify_by_loc(val, loc, pname):
    p = PARAMS[loc][pname]
    return classify(val, p["avg"], p["std"])

# ── FETCH FROM GOOGLE SHEETS ──────────────────────────────────────────────────
SHEET_ID = "1WyUxyGQBD9SJQNSQ7WK_KIKVLiU8EbG6e9cqiQMmI1g"
CSV_URL  = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

@st.cache_data(ttl=60, show_spinner="🔄 Mengambil data terbaru...")
def load_from_sheets():
    try:
        import io, requests
        resp = requests.get(CSV_URL)
        resp.encoding = "utf-8-sig"
        text = resp.text
        first_line = text.split("\n")[0]
        sep = ";" if first_line.count(";") > first_line.count(",") else ","
        df = pd.read_csv(io.StringIO(text), sep=sep, encoding_errors="replace")
        df.columns = df.columns.str.strip().str.replace("\ufeff", "", regex=False)
        return df, None
    except Exception as e:
        return None, str(e)

# ── COMPUTE ───────────────────────────────────────────────────────────────────
def prepare_df(df):
    df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
    df["_date"]  = pd.to_datetime(df["PDIcomp. Date"], errors="coerce", dayfirst=False).dt.strftime("%Y-%m-%d")
    df["_month"] = df["_date"].str[:7]
    df["_loc"]   = df["Model"].apply(get_loc)
    return df.dropna(subset=["_date"])

def calc_stats(df, sel_loc):
    if df.empty: return None

    result = {}
    for pname, col in FIELDS.items():
        if col not in df.columns:
            result[pname] = None
            continue

        vals = pd.to_numeric(df[col], errors="coerce")

        if sel_loc == "ALL":
            statuses = pd.Series([
                classify(val, PARAMS[loc][pname]["avg"], PARAMS[loc][pname]["std"])
                for val, loc in zip(vals, df["_loc"])
            ], index=df.index)
        else:
            p = PARAMS[sel_loc][pname]
            statuses = vals.apply(lambda v: classify(v, p["avg"], p["std"]))

        valid  = vals.dropna()
        fast   = int((statuses == "FAST").sum())
        normal = int((statuses == "NORMAL").sum())
        ng     = int((statuses == "NG").sum())
        na     = int(statuses.isna().sum())
        tc     = fast + normal + ng

        if sel_loc == "ALL":
            loc_counts = df["_loc"].value_counts()
            total_n = loc_counts.sum()
            param_avg = sum(PARAMS[loc][pname]["avg"] * cnt for loc, cnt in loc_counts.items()
                            if loc in PARAMS) / total_n if total_n else PARAMS["ALL"][pname]["avg"]
            param_std = sum(PARAMS[loc][pname]["std"] * cnt for loc, cnt in loc_counts.items()
                            if loc in PARAMS) / total_n if total_n else PARAMS["ALL"][pname]["std"]
            thresh_lo = param_avg - param_std
            thresh_hi = param_avg + param_std
        else:
            p = PARAMS[sel_loc][pname]
            param_avg, param_std = p["avg"], p["std"]
            thresh_lo = param_avg - param_std
            thresh_hi = param_avg + param_std

        result[pname] = {
            "fast": fast, "normal": normal, "ng": ng, "na": na,
            "total_classified": tc,
            "pct_fast":   round(fast/tc*100, 1)   if tc else 0,
            "pct_normal": round(normal/tc*100, 1) if tc else 0,
            "pct_ng":     round(ng/tc*100, 1)     if tc else 0,
            "achieved":   round((fast+normal)/tc*100, 1) if tc else None,
            "actual_avg": round(float(valid.mean()), 3) if not valid.empty else None,
            "actual_std": round(float(valid.std()), 3) if len(valid) > 1 else 0,
            "param_avg":  round(param_avg, 3),
            "param_std":  round(param_std, 3),
            "thresh_lo":  round(thresh_lo, 3),
            "thresh_hi":  round(thresh_hi, 3),
        }

    models = []
    for m, mdf in df.groupby("Model"):
        model_loc  = get_loc(m)
        use_loc = model_loc if sel_loc == "ALL" else sel_loc

        p   = PARAMS[use_loc]["Total"]
        col = FIELDS["Total"]
        tv  = pd.to_numeric(mdf[col], errors="coerce") if col in mdf.columns else pd.Series(dtype=float)
        sts = tv.apply(lambda v: classify(v, p["avg"], p["std"]))
        tc2 = int(sts.notna().sum())
        f2  = int((sts == "FAST").sum())
        n2  = int((sts == "NORMAL").sum())
        g2  = int((sts == "NG").sum())

        pv       = pd.to_numeric(mdf.get(FIELDS["PPO"],      pd.Series(dtype=float)), errors="coerce").dropna()
        rv       = pd.to_numeric(mdf.get(FIELDS["Receiving"],pd.Series(dtype=float)), errors="coerce").dropna()
        tvv      = tv.dropna()
        spuin_v  = pd.to_numeric(mdf.get(FIELDS["SPU In"],   pd.Series(dtype=float)), errors="coerce").dropna()
        spcomp_v = pd.to_numeric(mdf.get(FIELDS["SPU Comp"], pd.Series(dtype=float)), errors="coerce").dropna()
        models.append({
            "name": m, "n": len(mdf),
            "loc":      model_loc,
            "total":    round(float(tvv.mean()),      3) if not tvv.empty      else None,
            "ppo":      round(float(pv.mean()),       3) if not pv.empty       else None,
            "recv":     round(float(rv.mean()),       3) if not rv.empty       else None,
            "spu_in":   round(float(spuin_v.mean()),  3) if not spuin_v.empty  else None,
            "spu_comp": round(float(spcomp_v.mean()), 3) if not spcomp_v.empty else None,
            "fast": f2, "normal": n2, "ng": g2,
            "achieved": round((f2+n2)/tc2*100, 1) if tc2 else None,
        })
    models.sort(key=lambda x: x["total"] if x["total"] is not None else 999)

    t = result.get("Total")
    return {
        "total_units":  len(df),
        "models_count": df["Model"].nunique(),
        "ng_units":     t["ng"] if t else 0,
        "processes":    result,
        "models":       models,
    }

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#060a12;color:#e0e8ff}
[data-testid="stHeader"]{background:transparent}
.block-container{padding:1rem 2rem;max-width:1400px}
.kpi-box{background:linear-gradient(135deg,#0d1526,#111d35);border:1px solid rgba(100,160,255,.15);
  border-radius:12px;padding:16px 20px;text-align:center}
.kpi-n{font-size:2rem;font-weight:800;font-family:monospace}
.kpi-l{font-size:.7rem;color:#7a90bb;text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
.proc-card{background:#0d1526;border:1px solid rgba(100,160,255,.12);border-radius:10px;padding:14px 16px;margin-bottom:8px}
.proc-title{font-size:.75rem;font-weight:700;letter-spacing:.06em;margin-bottom:8px}
.stat-row{display:flex;justify-content:space-between;margin-bottom:4px}
.stat-l{font-size:.6rem;color:#7a90bb;text-transform:uppercase}
.stat-v{font-size:.65rem;font-weight:600;font-family:monospace}
.finding-card{background:#0d1526;border-radius:10px;border:1px solid rgba(100,160,255,.1);padding:12px 16px;margin-bottom:8px}
.section-title{font-size:.8rem;font-weight:700;color:#7fb3ff;text-transform:uppercase;
  letter-spacing:.08em;margin:20px 0 10px 0;border-bottom:1px solid rgba(100,160,255,.15);padding-bottom:6px}
div[data-testid="stMetric"]{background:#0d1526;border-radius:10px;padding:12px;border:1px solid rgba(100,160,255,.12)}
</style>
""", unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding:16px 0 8px 0'>
  <span style='font-size:1.1rem;font-weight:800;color:#7fb3ff;letter-spacing:.06em'>
    🚗 NLO1 DEPT — LEAD TIME STD DEV DASHBOARD
  </span>
  <span style='font-size:.6rem;color:#7a90bb;margin-left:12px'>PDIcomp. Date basis · Per-location parameter</span>
</div>
""", unsafe_allow_html=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔄 Data Source")
    st.caption("Data otomatis diambil dari Google Sheets")
    st.caption("Auto-refresh setiap 60 detik")

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption("NLO1 Dept · Lead Time Dashboard · 2026")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
df_raw, err = load_from_sheets()

if err:
    st.error(f"❌ Gagal load data dari Google Sheets: {err}")
    st.info("Pastikan Google Sheets sudah di-setup dengan benar.")
    st.stop()

if df_raw is None or df_raw.empty:
    st.warning("⚠️ Google Sheets kosong. Silakan isi data terlebih dahulu.")
    st.stop()

df = prepare_df(df_raw)

# ── FILTERS ───────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🔽 Filter</div>', unsafe_allow_html=True)

col_loc, col_mon, col_day = st.columns([2, 2, 4])

with col_loc:
    loc_opts   = ["ALL", "NVDC Cibitung", "NVDC Sunter", "NVDC Sunter Lexus"]
    loc_labels = {"ALL": "All", "NVDC Cibitung": "Cibitung",
                  "NVDC Sunter": "Sunter", "NVDC Sunter Lexus": "Lexus"}
    sel_loc = st.radio("Lokasi", loc_opts, format_func=lambda x: loc_labels[x],
                       horizontal=True, label_visibility="collapsed")

with col_mon:
    months      = sorted(df["_month"].dropna().unique().tolist())
    month_labels = {m: datetime.strptime(m, "%Y-%m").strftime("%b '%y") for m in months}
    sel_month   = st.radio("Bulan", months, format_func=lambda x: month_labels[x],
                           index=len(months)-1, horizontal=True, label_visibility="collapsed")

with col_day:
    dates_in_month = sorted(df[df["_month"] == sel_month]["_date"].dropna().unique().tolist())
    day_opts = ["ALL"] + dates_in_month
    def day_label(d):
        if d == "ALL": return "📅 All"
        dt = datetime.strptime(d, "%Y-%m-%d")
        days = ["Su","Mo","Tu","We","Th","Fr","Sa"]
        return f"{dt.day} {days[dt.weekday()]}"
    sel_date = st.radio("Tanggal", day_opts, format_func=day_label,
                        horizontal=True, label_visibility="collapsed")

# ── FILTER DATA ───────────────────────────────────────────────────────────────
df_loc  = df if sel_loc == "ALL" else df[df["_loc"] == sel_loc]
df_filt = df_loc[df_loc["_month"] == sel_month] if sel_date == "ALL" \
          else df_loc[df_loc["_date"] == sel_date]

stats = calc_stats(df_filt, sel_loc)
if not stats:
    st.warning("Tidak ada data untuk filter ini.")
    st.stop()

# ── PARAM NOTE ────────────────────────────────────────────────────────────────
param_desc = {
    "ALL":               "Per-location params (setiap model pakai param lokasinya masing-masing)",
    "NVDC Cibitung":     "Cibitung-specific (ALPHARD/CAMRY/HIACE/HILUX/LANDCRUISER/VELLFIRE/VOXY)",
    "NVDC Sunter":       "Sunter-specific (RUSH)",
    "NVDC Sunter Lexus": "Sunter Lexus-specific (LEXUS)",
}
date_label = sel_date if sel_date != "ALL" else month_labels.get(sel_month, sel_month)
st.caption(f"📐 Param: {param_desc[sel_loc]} | 📅 {date_label}")

# ── KPI CARDS ─────────────────────────────────────────────────────────────────
t_proc = stats["processes"].get("Total")
ach    = t_proc["achieved"] if t_proc else None

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#7fb3ff">{stats['total_units']:,}</div>
        <div class="kpi-l">Total Units</div></div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#00e5a0">{stats['models_count']}</div>
        <div class="kpi-l">Models</div></div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="kpi-box">
        <div class="kpi-n" style="color:#ff4060">{stats['ng_units']}</div>
        <div class="kpi-l">Over L/T</div></div>""", unsafe_allow_html=True)

# ── OVERALL ACHIEVEMENT ───────────────────────────────────────────────────────
st.markdown('<div class="section-title">📊 Overall L/T Achievement</div>', unsafe_allow_html=True)
if t_proc:
    ach_val   = ach or 0
    color     = ach_color(ach)
    thresh_lo = t_proc["thresh_lo"]
    thresh_hi = t_proc["thresh_hi"]
    st.markdown(f"""
    <div style='background:#111d35;border-radius:10px;padding:16px 20px;border:1px solid rgba(100,160,255,.15)'>
      <div style='display:flex;justify-content:space-between;margin-bottom:8px'>
        <span style='font-size:2.2rem;font-weight:800;color:{color}'>{ach_val:.1f}%</span>
        <span style='color:#7a90bb;font-size:.7rem;align-self:center'>
          {"Per-location classification" if sel_loc == "ALL" else f"FAST ≤{to_mins(thresh_lo)} min · NORMAL {to_mins(thresh_lo)}–{to_mins(thresh_hi)} min · Over >{to_mins(thresh_hi)} min"}
        </span>
      </div>
      <div style='display:flex;height:24px;border-radius:6px;overflow:hidden;gap:2px'>
        <div style='width:{t_proc["pct_fast"]}%;background:#00e5a0;display:flex;align-items:center;
          justify-content:center;font-size:.55rem;font-weight:700;color:#0a0f1e'>{t_proc["pct_fast"]:.0f}%</div>
        <div style='width:{t_proc["pct_normal"]}%;background:#3d9bff;display:flex;align-items:center;
          justify-content:center;font-size:.55rem;font-weight:700;color:#0a0f1e'>{t_proc["pct_normal"]:.0f}%</div>
        <div style='width:{t_proc["pct_ng"]}%;background:#ff4060;display:flex;align-items:center;
          justify-content:center;font-size:.55rem;font-weight:700;color:#fff'>{t_proc["pct_ng"]:.0f}%</div>
      </div>
      <div style='display:flex;gap:16px;margin-top:8px;font-size:.6rem;color:#7a90bb'>
        <span>🟢 FAST: {t_proc["fast"]} units</span>
        <span>🔵 NORMAL: {t_proc["normal"]} units</span>
        <span>🔴 Over L/T: {t_proc["ng"]} units</span>
        <span>avg {fmt_mins(t_proc["actual_avg"])}</span>
      </div>
    </div>""", unsafe_allow_html=True)

# ── PROCESS CARDS ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">⚙️ Per Process</div>', unsafe_allow_html=True)
proc_cols = st.columns(5)
for i, (pname, color) in enumerate(PROC_COLORS.items()):
    p = stats["processes"].get(pname)
    with proc_cols[i]:
        if not p:
            st.markdown(f"""<div class="proc-card" style="border-color:{color}40">
                <div class="proc-title" style="color:{color}">{pname}</div>
                <div style="color:#555;font-size:.6rem">N/A</div></div>""", unsafe_allow_html=True)
            continue
        ach_p = p["achieved"] or 0
        st.markdown(f"""<div class="proc-card" style="border-color:{color}50">
          <div class="proc-title" style="color:{color}">{pname}</div>
          <div style="font-size:1.4rem;font-weight:800;color:{ach_color(p['achieved'])};
            font-family:monospace;margin-bottom:6px">{ach_p:.1f}%</div>
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
          <div style="margin-top:8px;font-size:.55rem;display:flex;justify-content:space-between;color:#7a90bb">
            <span style="color:#00e5a0">≤{to_mins(p['thresh_lo'])}</span>
            <span>{'weighted' if sel_loc == 'ALL' else 'min'}</span>
            <span style="color:#ff4060">&gt;{to_mins(p['thresh_hi'])}</span>
          </div>
          <div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:4px;gap:1px">
            <div style="width:{p['pct_fast']}%;background:#00e5a0"></div>
            <div style="width:{p['pct_normal']}%;background:#3d9bff"></div>
            <div style="width:{p['pct_ng']}%;background:#ff4060"></div>
          </div>
        </div>""", unsafe_allow_html=True)

# ── BOTTOM SECTION ────────────────────────────────────────────────────────────
left_col, right_col = st.columns([3, 2])

with left_col:
    # Model Table
    st.markdown('<div class="section-title">🚗 Model Summary</div>', unsafe_allow_html=True)
    if stats["models"]:
        mdf = pd.DataFrame(stats["models"])
        mdf["Avg L/T"]      = mdf["total"].apply(fmt_mins)
        mdf["Avg PPO"]      = mdf["ppo"].apply(fmt_mins)
        mdf["Avg Recv"]     = mdf["recv"].apply(fmt_mins)
        mdf["Avg SPU In"]   = mdf["spu_in"].apply(fmt_mins)
        mdf["Avg SPU Comp"] = mdf["spu_comp"].apply(fmt_mins)
        mdf["Achievement"]  = mdf["achieved"].apply(lambda x: f"{x:.1f}%" if x is not None else "—")
        mdf["Over L/T"]     = mdf["ng"]
        st.dataframe(
            mdf[["name","n","Achievement","Over L/T","Avg L/T","Avg Recv","Avg PPO","Avg SPU In","Avg SPU Comp"]].rename(
                columns={"name":"Model","n":"Units"}),
            use_container_width=True, hide_index=True)

    # Daily Table
    if sel_date == "ALL":
        st.markdown('<div class="section-title">📅 Daily Achievement</div>', unsafe_allow_html=True)
        daily_rows = []
        for d in dates_in_month:
            d_df = df_loc[df_loc["_date"] == d]
            if d_df.empty: continue
            ds = calc_stats(d_df, sel_loc)
            if not ds: continue
            t = ds["processes"].get("Total")
            dt = datetime.strptime(d, "%Y-%m-%d")
            days_id = ["Min","Sen","Sel","Rab","Kam","Jum","Sab"]
            daily_rows.append({
                "Tanggal":     f"{dt.day} {days_id[dt.weekday()]}",
                "Units":       ds["total_units"],
                "Over L/T":    ds["ng_units"],
                "Achievement": f"{t['achieved']:.1f}%" if t and t["achieved"] is not None else "—",
                "Avg L/T":     fmt_mins(t["actual_avg"]) if t else "—",
            })
        if daily_rows:
            st.dataframe(pd.DataFrame(daily_rows), use_container_width=True, hide_index=True)

with right_col:
    # Key Findings & Action Points
    st.markdown('<div class="section-title">💡 Key Findings & Action Points</div>', unsafe_allow_html=True)
    st.caption(f"Auto-generated · {sel_loc} · {date_label}")

    findings  = []
    total_p   = stats["processes"].get("Total")
    recv_p    = stats["processes"].get("Receiving")
    ppo_p     = stats["processes"].get("PPO")
    spuin_p   = stats["processes"].get("SPU In")

    # 1) Overall achievement
    if total_p and total_p["achieved"] is not None:
        a = total_p["achieved"]
        if a >= 99:
            findings.append({"ico":"✅","color":"#00e5a0",
                "title":"Total L/T Achievement Excellent",
                "desc":f"{a}% of {total_p['total_classified']} units within parameter. All processes running smoothly.",
                "badge":f"{a}%","action":None})
        elif a >= 95:
            findings.append({"ico":"📊","color":"#00e5a0",
                "title":"Total L/T Achievement Good",
                "desc":f"{a}% achieved ({total_p['fast']+total_p['normal']}/{total_p['total_classified']} units). {total_p['ng']} Over L/T units need attention.",
                "badge":f"{a}%",
                "action":f"Monitor {total_p['ng']} Over L/T units — identify common models/process causing delay."})
        elif a >= 90:
            findings.append({"ico":"⚠️","color":"#ffcc40",
                "title":"Total L/T Below Target",
                "desc":f"{a}% achieved — {total_p['ng']} units Over L/T ({total_p['pct_ng']}%). Avg actual {fmt_mins(total_p['actual_avg'])} vs param avg {fmt_mins(total_p['param_avg'])}.",
                "badge":f"{a}%",
                "action":f"Investigasi {total_p['ng']} unit Over L/T. Cek proses bottleneck dan koordinasi dengan team terkait."})
        else:
            findings.append({"ico":"🚨","color":"#ff4060",
                "title":"CRITICAL: Total L/T Below 90%",
                "desc":f"Only {a}% achieved — {total_p['ng']} units Over L/T ({total_p['pct_ng']}%). Avg {fmt_mins(total_p['actual_avg'])} significantly above param.",
                "badge":f"{a}%",
                "action":f"URGENT: Immediate escalation required. Review all {total_p['ng']} Over L/T units and identify root cause by process stage."})

    # 2) Worst process
    procs_list = [(n, p) for n, p in [("Receiving",recv_p),("PPO",ppo_p),("SPU In",spuin_p)]
                  if p and p["achieved"] is not None]
    if procs_list:
        procs_list.sort(key=lambda x: x[1]["achieved"])
        wname, wp = procs_list[0]
        if wp["achieved"] < 90:
            findings.append({"ico":"🔴","color":"#ff4060",
                "title":f"{wname} — Bottleneck Proses",
                "desc":f"Achievement {wp['achieved']}% ({wp['ng']} Over L/T, {wp['pct_ng']}%). Actual avg {fmt_mins(wp['actual_avg'])} vs param {fmt_mins(wp['param_avg'])}. Std dev ±{to_mins(wp['actual_std'])} min vs param ±{to_mins(wp['param_std'])} min.",
                "badge":f"{wp['achieved']}%",
                "action":f"Review step {wname}: cek penyebab delay — ada unit tunggu part/kesiapan bay? Bandingkan unit Over vs On-time untuk identifikasi pola."})
        elif wp["achieved"] < 95:
            findings.append({"ico":"🟡","color":"#ffcc40",
                "title":f"{wname} — Monitor Lebih Dekat",
                "desc":f"Achievement {wp['achieved']}% — masih ada {wp['ng']} Over L/T ({wp['pct_ng']}%). Avg actual {fmt_mins(wp['actual_avg'])}.",
                "badge":f"{wp['achieved']}%",
                "action":f"Keep monitoring {wname}. Jika trend memburuk, review allocation bay dan jadwal tim."})

    # 3) Best process
    if len(procs_list) > 1:
        procs_list.sort(key=lambda x: x[1]["achieved"], reverse=True)
        bname, bp = procs_list[0]
        if bp["achieved"] >= 98:
            findings.append({"ico":"🟢","color":"#00e5a0",
                "title":f"{bname} — Proses Terbaik",
                "desc":f"Achievement {bp['achieved']}% — sangat baik. Avg actual {fmt_mins(bp['actual_avg'])} (param {fmt_mins(bp['param_avg'])}). Jadikan benchmark.",
                "badge":f"{bp['achieved']}%","action":None})

    # 4) Problem models
    prob_models = sorted([m for m in stats["models"] if m["ng"] and m["ng"] > 0
                          and m["achieved"] is not None], key=lambda x: x["achieved"])
    if prob_models:
        top = prob_models[0]
        findings.append({"ico":"🚗","color":ach_color(top["achieved"]),
            "title":f"{top['name']} — Model Paling Bermasalah",
            "desc":f"{top['ng']} Over L/T dari {top['n']} units (ach. {top['achieved']}%). Avg Total L/T {fmt_mins(top['total'])}, avg PPO {fmt_mins(top['ppo'])}.",
            "badge":f"{top['achieved']}%",
            "action":f"Prioritaskan investigasi {top['name']}: apakah ada pola di hari/shift tertentu? Cek avg PPO {fmt_mins(top['ppo'])} vs param."})
        if len(prob_models) > 1:
            others = ", ".join([f"{m['name']} ({m['ng']})" for m in prob_models[1:3]])
            findings.append({"ico":"📋","color":"#a066ff",
                "title":"Model Lain Dengan Over L/T",
                "desc":f"{others} juga terdampak. Total {sum(m['ng'] for m in prob_models[1:])} unit Over L/T di semua model lainnya.",
                "badge":f"{len(prob_models)} models",
                "action":"Cross-check apakah masalah berkaitan dengan batch delivery atau kondisi khusus hari ini."})

    # 5) High std dev
    for pn, p in stats["processes"].items():
        if p and p["actual_std"] and p["param_std"] and p["param_std"] > 0:
            ratio = p["actual_std"] / p["param_std"]
            if ratio > 1.5:
                findings.append({"ico":"📈","color":"#22d3ee",
                    "title":f"{pn} — Variabilitas Tinggi",
                    "desc":f"Std dev aktual ±{to_mins(p['actual_std'])} min ({round((ratio-1)*100)}% di atas param ±{to_mins(p['param_std'])} min). Indikasi konsistensi proses perlu perbaikan.",
                    "badge":f"±{to_mins(p['actual_std'])} min",
                    "action":f"Analisa distribusi waktu proses {pn}. Std dev tinggi berarti ada unit yang jauh di atas rata-rata — identifikasi outlier tersebut."})
                break

    # 6) All perfect
    if not findings:
        findings.append({"ico":"🏆","color":"#00e5a0",
            "title":"Outstanding Performance!",
            "desc":f"Semua unit dalam parameter untuk filter yang dipilih. Achievement sempurna — {stats['total_units']} units diproses tepat waktu.",
            "badge":"100%","action":None})

    for f in findings:
        action_part = (
            f"<div style='margin-top:6px;padding:6px 8px;background:rgba(255,255,255,.04);"
            f"border-radius:4px;font-size:.58rem;color:#ffcc40;line-height:1.5'>"
            f"→ <b>Action:</b> {f['action']}</div>"
        ) if f.get("action") else ""

        card_html = (
            f"<div class='finding-card' style='border-left:3px solid {f['color']}'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px'>"
            f"<div style='font-size:.68rem;font-weight:700;color:{f['color']}'>{f['ico']} {f['title']}</div>"
            f"<div style='font-size:.6rem;font-weight:700;color:{f['color']};background:rgba(255,255,255,.06);"
            f"padding:2px 8px;border-radius:10px'>{f['badge']}</div>"
            f"</div>"
            f"<div style='font-size:.61rem;color:#a0b4cc;line-height:1.5'>{f['desc']}</div>"
            + action_part +
            f"</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)

# ── CHATBOT ───────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🤖 Tanya Data Dashboard</div>', unsafe_allow_html=True)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

def build_data_context(stats, sel_loc, sel_month, sel_date, df_filt):
    ctx = f"""Kamu adalah asisten analisis data untuk NLO1 Dept - Toyota Astra Motor.
Jawab dalam Bahasa Indonesia, singkat dan langsung ke poin. Gunakan data berikut untuk menjawab pertanyaan.

=== FILTER AKTIF ===
Lokasi: {sel_loc}
Bulan: {sel_month}
Tanggal: {sel_date}
Total Units: {stats['total_units']}
Jumlah Model: {stats['models_count']}
Over L/T: {stats['ng_units']}
"""
    t = stats["processes"].get("Total")
    if t:
        ctx += f"""
=== TOTAL L/T ===
Achievement: {t['achieved']}%
FAST: {t['fast']} units ({t['pct_fast']}%)
NORMAL: {t['normal']} units ({t['pct_normal']}%)
Over L/T (NG): {t['ng']} units ({t['pct_ng']}%)
Actual Avg: {fmt_mins(t['actual_avg'])}
Param Avg: {fmt_mins(t['param_avg'])}
Actual Std Dev: ±{to_mins(t['actual_std'])} min
Param Std Dev: ±{to_mins(t['param_std'])} min
Threshold FAST: ≤{to_mins(t['thresh_lo'])} min
Threshold Over: >{to_mins(t['thresh_hi'])} min
"""
    ctx += "\n=== PER PROSES ===\n"
    for pname in ["Receiving", "PPO", "SPU In", "SPU Comp"]:
        p = stats["processes"].get(pname)
        if p:
            ctx += (f"{pname}: achievement={p['achieved']}%, "
                    f"actual_avg={fmt_mins(p['actual_avg'])}, "
                    f"param_avg={fmt_mins(p['param_avg'])}, "
                    f"actual_std=±{to_mins(p['actual_std'])} min, "
                    f"over={p['ng']} units ({p['pct_ng']}%)\n")

    ctx += "\n=== PER MODEL ===\n"
    for m in stats["models"]:
        ctx += (f"{m['name']}: {m['n']} units, lokasi={m['loc']}, "
                f"achievement={m['achieved']}%, avg_total={fmt_mins(m['total'])}, "
                f"avg_ppo={fmt_mins(m['ppo'])}, avg_recv={fmt_mins(m['recv'])}, "
                f"over={m['ng']} units\n")

    return ctx

# Tampilkan chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Tanya sesuatu... contoh: 'model mana paling banyak Over L/T?' atau 'analisis proses PPO'"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Menganalisis data..."):
            try:
                import requests as req

                system_prompt = build_data_context(stats, sel_loc, sel_month, sel_date, df_filt)
                messages_payload = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_history
                ]

                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama3-8b-8192",
                        "max_tokens": 1000,
                        "messages": [{"role": "system", "content": system_prompt}] + messages_payload,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                answer = resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                try:
                    err_detail = resp.json()
                except:
                    err_detail = "no detail"
                answer = f"❌ Error: {str(e)} | Detail: {err_detail}"

        st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})

# Tombol clear chat
if st.session_state.chat_history:
    if st.button("🗑️ Clear Chat", use_container_width=False):
        st.session_state.chat_history = []
        st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center;padding:20px 0;color:#3a4a6a;font-size:.55rem'>
  NLO1 Dept · Lead Time Std Dev Dashboard · Data source: Google Sheets · Auto-refresh every 60s
</div>""", unsafe_allow_html=True)
