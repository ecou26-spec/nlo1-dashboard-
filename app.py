import os
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
        "Receiving": {"avg": 1.74,  "std": 0.49},
        "PPO":       {"avg": 2.86,  "std": 0.72},
        "SPU In":    {"avg": 1.01,  "std": 0.25},
        "SPU Comp":  {"avg": 0.80,  "std": 0.20},
        "Total":     {"avg": 6.46,  "std": 1.67},
    },
    "NVDC Cibitung": {
        "Receiving": {"avg": 1.174, "std": 0.29},
        "PPO":       {"avg": 1.934, "std": 0.53},
        "SPU In":    {"avg": 1.571, "std": 0.40},
        "SPU Comp":  {"avg": 0.934, "std": 0.23},
        "Total":     {"avg": 6.079, "std": 1.52},
    },
    "NVDC Sunter": {
        "Receiving": {"avg": 5.0,   "std": 1.25},
        "PPO":       {"avg": 1.75,  "std": 0.43},
        "SPU In":    {"avg": 1.0,   "std": 0.25},
        "SPU Comp":  {"avg": 0.75,  "std": 0.19},
        "Total":     {"avg": 8.50,  "std": 2.13},
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

# ── DATE PARSING ──────────────────────────────────────────────────────────────
def parse_date_series(series):
    """
    Parse date series — prioritize ISO (from raw CSV), fallback to slash formats.
    Auto-detects D/M vs M/D from data to handle Google Sheets locale conversion.
    """
    raw = series.astype(str).str.strip()
    result = pd.Series([pd.NaT] * len(raw), index=raw.index, dtype="datetime64[ns]")

    # ISO first — always unambiguous (format from raw CSV source)
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
        mask = result.isna()
        if not mask.any(): break
        result[mask] = pd.to_datetime(raw[mask], format=fmt, errors="coerce")

    # Slash format fallback (Google Sheets export)
    remaining = raw[result.isna() & raw.str.match(r"^\d{1,2}/\d{1,2}/\d{4}")]
    if not remaining.empty:
        day_first = False
        for v in remaining.head(200):
            parts = v.split("/")
            if len(parts) < 2: continue
            first  = int(parts[0]) if parts[0].isdigit() else 0
            second = int(parts[1]) if parts[1].isdigit() else 0
            if first > 12:  day_first = True;  break
            if second > 12: day_first = False; break
        slash_fmts = (["%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"]
                      if day_first else
                      ["%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"])
        for fmt in slash_fmts:
            mask = result.isna()
            if not mask.any(): break
            result[mask] = pd.to_datetime(raw[mask], format=fmt, errors="coerce")

    return result

# ── COMPUTE ───────────────────────────────────────────────────────────────────
def prepare_df(df):
    df.columns = df.columns.str.strip().str.replace('\ufeff', '', regex=False)
    df["_date"]  = parse_date_series(df["PDIcomp. Date"]).dt.strftime("%Y-%m-%d")
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
        model_loc = get_loc(m)
        use_loc   = model_loc if sel_loc == "ALL" else sel_loc

        p   = PARAMS[use_loc]["Total"]
        col = FIELDS["Total"]
        tv  = pd.to_numeric(mdf[col], errors="coerce") if col in mdf.columns else pd.Series(dtype=float)
        sts = tv.apply(lambda v: classify(v, p["avg"], p["std"]))
        tc2 = int(sts.notna().sum())
        f2  = int((sts == "FAST").sum())
        n2  = int((sts == "NORMAL").sum())
        g2  = int((sts == "NG").sum())

        pv       = pd.to_numeric(mdf.get(FIELDS["PPO"],       pd.Series(dtype=float)), errors="coerce").dropna()
        rv       = pd.to_numeric(mdf.get(FIELDS["Receiving"], pd.Series(dtype=float)), errors="coerce").dropna()
        tvv      = tv.dropna()
        spuin_v  = pd.to_numeric(mdf.get(FIELDS["SPU In"],    pd.Series(dtype=float)), errors="coerce").dropna()
        spcomp_v = pd.to_numeric(mdf.get(FIELDS["SPU Comp"],  pd.Series(dtype=float)), errors="coerce").dropna()
        models.append({
            "name": m, "n": len(mdf), "loc": model_loc,
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

# ── FIFO CALCULATION ──────────────────────────────────────────────────────────
def calc_fifo(df_input, ppoin_col, tolerance_min=240):
    """
    FIFO compliance check — port dari DAX FIFO_Model_%.

    Logic:
    Unit i = Non-FIFO jika ada unit j dengan MODEL SAMA dan HARI SAMA dimana:
      - pdi_j < pdi_i  (j masuk PDI lebih awal)
      - ppo_j > ppo_i + tolerance  (j keluar PPO lebih lambat)
    Artinya i menyalip antrian j.

    Scope per hari (bukan per bulan) — unit beda hari tidak saling dibandingkan
    karena setiap hari adalah sesi operasional terpisah.
    """
    tol = pd.Timedelta(minutes=tolerance_min)

    fifo_df = df_input[["Model", "_date", "PDIcomp. Date", ppoin_col]].copy()
    fifo_df["_pdi"] = parse_date_series(fifo_df["PDIcomp. Date"])
    fifo_df["_ppo"] = parse_date_series(fifo_df[ppoin_col])
    fifo_df = fifo_df.dropna(subset=["_pdi", "_ppo"])

    if fifo_df.empty:
        return None

    non_fifo_flags = []
    # Group by model + date — FIFO hanya dibandingkan dalam hari & model yang sama
    for (model, date), grp in fifo_df.groupby(["Model", "_date"]):
        for _, cur in grp.iterrows():
            violators = grp[
                (grp["_pdi"] <  cur["_pdi"]) &
                (grp["_ppo"] >  cur["_ppo"] + tol)
            ]
            non_fifo_flags.append({
                "idx":       cur.name,
                "non_fifo":  len(violators) > 0,
                "model":     model,
                "date":      date,
            })

    flags_df = pd.DataFrame(non_fifo_flags).set_index("idx")
    fifo_df["_non_fifo"] = flags_df["non_fifo"]
    fifo_df["_model"]    = flags_df["model"]
    fifo_df["_day"]      = flags_df["date"]

    return fifo_df

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#060a12;color:#e0e8ff}
[data-testid="stHeader"]{background:transparent}
.block-container{padding:1rem 2rem;max-width:1200px;margin-right:240px}
#chat-panel{position:fixed;top:60px;right:0;width:220px;height:calc(100vh - 60px);
  background:#0a1020;border-left:1px solid rgba(100,160,255,.2);
  display:flex;flex-direction:column;z-index:999;padding:12px}
#chat-messages{flex:1;overflow-y:auto;margin-bottom:8px;padding-right:4px}
#chat-messages::-webkit-scrollbar{width:3px}
#chat-messages::-webkit-scrollbar-thumb{background:#1e3a6e;border-radius:3px}
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
    st.markdown("### 📂 Upload Data CSV")
    uploaded_csv = st.file_uploader(
        "Upload CSV langsung (recommended)",
        type=["csv"],
        help="Format ISO dari file asli terbaca sempurna. Hindari konversi tanggal oleh Google Sheets."
    )
    st.markdown("### 🔄 Google Sheets")
    st.caption("Fallback otomatis jika tidak ada CSV")
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
if uploaded_csv is not None:
    try:
        import io
        df_raw = pd.read_csv(uploaded_csv, encoding="utf-8-sig", encoding_errors="replace")
        df_raw.columns = df_raw.columns.str.strip().str.replace("\ufeff", "", regex=False)
        err = None
        st.sidebar.success(f"✅ CSV: {len(df_raw):,} rows")
    except Exception as e:
        df_raw, err = None, str(e)
else:
    df_raw, err = load_from_sheets()

if err:
    st.error(f"❌ Gagal load data: {err}")
    st.info("Upload CSV atau pastikan Google Sheets sudah di-setup dengan benar.")
    st.stop()

if df_raw is None or df_raw.empty:
    st.warning("⚠️ Data kosong. Upload CSV atau pastikan Google Sheets sudah terisi.")
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
    months       = sorted(df["_month"].dropna().unique().tolist())
    month_labels = {m: datetime.strptime(m, "%Y-%m").strftime("%b '%y") for m in months}
    sel_month    = st.radio("Bulan", months, format_func=lambda x: month_labels[x],
                            index=len(months)-1, horizontal=True, label_visibility="collapsed")

with col_day:
    dates_in_month = sorted(df[df["_month"] == sel_month]["_date"].dropna().unique().tolist())
    day_opts = ["ALL"] + dates_in_month
    def day_label(d):
        if d == "ALL": return "📅 All"
        dt = datetime.strptime(d, "%Y-%m-%d")
        days = ["Mo","Tu","We","Th","Fr","Sa","Su"]
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
            <span class="stat-l">Actual Lead Time</span>
            <span class="stat-v" style="color:{color}">{fmt_mins(p['actual_avg'])}</span>
          </div>
          <div class="stat-row">
            <span class="stat-l">Target Lead Time</span>
            <span class="stat-v" style="color:#7a90bb">{fmt_mins(p['param_avg'])}</span>
          </div>
          <div class="stat-row">
            <span class="stat-l">Actual Variation</span>
            <span class="stat-v" style="color:{color}">±{to_mins(p['actual_std'])} min</span>
          </div>
          <div class="stat-row">
            <span class="stat-l">Standard Variation</span>
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
    # ── Model Table ──────────────────────────────────────────────────────────
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

    # ── Daily Table ──────────────────────────────────────────────────────────
    if sel_date == "ALL":
        st.markdown('<div class="section-title">📅 Daily Achievement</div>', unsafe_allow_html=True)
        daily_rows = []
        for d in dates_in_month:
            d_df = df_loc[df_loc["_date"] == d]
            if d_df.empty: continue
            ds = calc_stats(d_df, sel_loc)
            if not ds: continue
            t  = ds["processes"].get("Total")
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

    # ── FIFO Compliance ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🔄 FIFO Compliance — PDIcomp. (In) vs PPOin (Out)</div>', unsafe_allow_html=True)

    # Detect PPOin Date column
    ppoin_col = None
    for candidate in ["PPOin Date", "PPOin. Date", "PPO in Date", "PPOIn Date"]:
        if candidate in df_filt.columns:
            ppoin_col = candidate
            break

    if ppoin_col is None:
        st.caption("⚠️ Kolom 'PPOin Date' tidak ditemukan di data.")
    else:
        fifo_tol = 1440  # hardcode 1440 menit


        with st.spinner("Menghitung FIFO compliance..."):
            fifo_df = calc_fifo(df_filt, ppoin_col, tolerance_min=fifo_tol)

        if fifo_df is None or fifo_df.empty:
            st.caption("⚠️ Tidak ada data FIFO valid untuk filter ini.")
        else:
            # ── Per-model summary ────────────────────────────────────────────
            fifo_by_model = []
            for model, grp in fifo_df.groupby("_model"):
                total = len(grp)
                nf    = int(grp["_non_fifo"].sum())
                ok    = total - nf
                pct   = round(ok / total * 100, 1) if total else 0
                fifo_by_model.append({
                    "Model": model, "Total": total,
                    "FIFO_OK": ok, "NonFIFO": nf, "FIFO_Pct": pct
                })
            fifo_by_model = sorted(fifo_by_model, key=lambda x: x["FIFO_Pct"])

            # Bar chart
            st.markdown("""
            <div style='background:#0d1526;border:1px solid rgba(100,160,255,.12);
              border-radius:10px;padding:14px 16px;'>
              <div style='display:grid;grid-template-columns:90px 1fr 60px 65px 55px;
                gap:4px;font-size:.57rem;color:#7a90bb;text-transform:uppercase;
                letter-spacing:.05em;margin-bottom:8px;padding-bottom:6px;
                border-bottom:1px solid rgba(100,160,255,.1)'>
                <span>Model</span><span>FIFO Compliance</span>
                <span style='text-align:right'>FIFO%</span>
                <span style='text-align:right'>Non-FIFO</span>
                <span style='text-align:right'>Units</span>
              </div>
            """, unsafe_allow_html=True)

            for row in fifo_by_model:
                pct       = row["FIFO_Pct"]
                bar_color = "#00e5a0" if pct >= 95 else ("#ffcc40" if pct >= 85 else "#ff4060")
                ng_color  = "#ff4060" if row["NonFIFO"] > 0 else "#3a4a6a"
                st.markdown(f"""
                <div style='display:grid;grid-template-columns:90px 1fr 60px 65px 55px;
                  gap:4px;align-items:center;margin-bottom:5px'>
                  <span style='font-size:.61rem;font-weight:600;color:#e0e8ff;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis'
                    title='{row["Model"]}'>{row["Model"]}</span>
                  <div style='background:#0a1525;border-radius:3px;height:14px;position:relative'>
                    <div style='width:{pct:.1f}%;background:{bar_color};height:100%;border-radius:3px'></div>
                  </div>
                  <span style='font-size:.62rem;font-weight:700;font-family:monospace;
                    color:{bar_color};text-align:right'>{pct:.1f}%</span>
                  <span style='font-size:.62rem;font-family:monospace;
                    color:{ng_color};text-align:right'>{row["NonFIFO"]} unit</span>
                  <span style='font-size:.62rem;font-family:monospace;
                    color:#7a90bb;text-align:right'>{row["Total"]}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # Overall KPIs
            total_all = len(fifo_df)
            nf_all    = int(fifo_df["_non_fifo"].sum())
            ok_all    = total_all - nf_all
            pct_all   = round(ok_all / total_all * 100, 1) if total_all else 0
            c_pct     = "#00e5a0" if pct_all >= 95 else ("#ffcc40" if pct_all >= 85 else "#ff4060")

            cf1, cf2, cf3 = st.columns(3)
            with cf1:
                st.markdown(f"""<div class='kpi-box' style='padding:10px 14px;margin-top:8px'>
                  <div class='kpi-n' style='font-size:1.4rem;color:{c_pct}'>{pct_all}%</div>
                  <div class='kpi-l'>Overall FIFO Compliance</div></div>""", unsafe_allow_html=True)
            with cf2:
                st.markdown(f"""<div class='kpi-box' style='padding:10px 14px;margin-top:8px'>
                  <div class='kpi-n' style='font-size:1.4rem;color:#ff4060'>{nf_all}</div>
                  <div class='kpi-l'>Units Non-FIFO</div></div>""", unsafe_allow_html=True)
            with cf3:
                st.markdown(f"""<div class='kpi-box' style='padding:10px 14px;margin-top:8px'>
                  <div class='kpi-n' style='font-size:1.4rem;color:#00e5a0'>{ok_all}</div>
                  <div class='kpi-l'>Units FIFO OK</div></div>""", unsafe_allow_html=True)

            scope_note = "per hari" if sel_date == "ALL" else f"tanggal {sel_date}"
            st.caption(f"🟢 ≥95% · 🟡 85–95% · 🔴 <85% | Non-FIFO = Advance / Delay Unit")

with right_col:
    # ── Key Findings & Action Points ─────────────────────────────────────────
    st.markdown('<div class="section-title">💡 Key Findings & Action Points</div>', unsafe_allow_html=True)
    st.caption(f"Auto-generated · {sel_loc} · {date_label}")

    findings = []
    total_p  = stats["processes"].get("Total")
    recv_p   = stats["processes"].get("Receiving")
    ppo_p    = stats["processes"].get("PPO")
    spuin_p  = stats["processes"].get("SPU In")

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
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

def build_data_context(stats, sel_loc, sel_month, sel_date, df_filt):
    t = stats["processes"].get("Total")
    lines = [
        "Kamu adalah asisten analisis data NLO1 Dept - Toyota Astra Motor. Jawab Bahasa Indonesia, singkat.",
        f"Filter: {sel_loc} | {sel_month} | {sel_date}",
        f"Units: {stats['total_units']} | Models: {stats['models_count']} | Over L/T: {stats['ng_units']}",
    ]
    if t:
        lines.append(f"Total Achievement: {t['achieved']}% | FAST:{t['fast']} NORMAL:{t['normal']} NG:{t['ng']}")
        lines.append(f"Avg actual: {fmt_mins(t['actual_avg'])} | Avg param: {fmt_mins(t['param_avg'])}")
    lines.append("Per Proses:")
    for pname in ["Receiving", "PPO", "SPU In", "SPU Comp"]:
        p = stats["processes"].get(pname)
        if p:
            lines.append(f"  {pname}: {p['achieved']}% ach | avg {fmt_mins(p['actual_avg'])} | NG {p['ng']} units")
    lines.append("Per Model:")
    for m in stats["models"]:
        lines.append(f"  {m['name']}: {m['n']} unit | ach {m['achieved']}% | avg {fmt_mins(m['total'])} | NG {m['ng']}")
    return "\n".join(lines)

def ask_ai(prompt, stats, sel_loc, sel_month, sel_date, df_filt):
    import requests as req
    import time
    system_prompt = build_data_context(stats, sel_loc, sel_month, sel_date, df_filt)
    cf_account = st.secrets.get("CF_ACCOUNT_ID", st.secrets.get("cf_account_id", ""))
    cf_token   = st.secrets.get("CF_API_TOKEN",  st.secrets.get("cf_api_token",  ""))
    for attempt in range(3):
        try:
            resp = req.post(
                f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/run/@cf/meta/llama-3.1-8b-instruct",
                headers={"Authorization": f"Bearer {cf_token}", "Content-Type": "application/json"},
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": prompt}
                    ],
                    "max_tokens": 600,
                },
                timeout=40,
            )
            if resp.status_code == 429:
                time.sleep((attempt + 1) * 5)
                continue
            resp.raise_for_status()
            return resp.json()["result"]["response"]
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(5)
    return "❌ Gagal setelah 3 percobaan. Coba lagi beberapa saat."

chat_msgs_html = ""
for msg in st.session_state.chat_history:
    is_user = msg["role"] == "user"
    bg      = "rgba(61,155,255,.2)" if is_user else "rgba(160,102,255,.15)"
    align   = "flex-end" if is_user else "flex-start"
    icon    = "👤" if is_user else "🤖"
    chat_msgs_html += f"""
    <div style='display:flex;justify-content:{align};margin-bottom:6px'>
    <div style='background:{bg};border-radius:8px;padding:6px 10px;
    font-size:.6rem;color:#e0e8ff;max-width:90%;line-height:1.5'>
    {icon} {msg["content"]}</div></div>"""

st.markdown(f"""
<div id='chat-panel'>
  <div style='font-size:.68rem;font-weight:700;color:#7fb3ff;letter-spacing:.06em;
  border-bottom:1px solid rgba(100,160,255,.15);padding-bottom:5px;margin-bottom:6px'>
  🤖 AI ASSISTANT</div>
  <div id='chat-messages'>{chat_msgs_html if chat_msgs_html else "<div style=\'color:#3a4a6a;font-size:.58rem;text-align:center;margin-top:40px\'>Tanya sesuatu tentang data dashboard...</div>"}</div>
  <div style='font-size:.5rem;color:#3a4a6a;text-align:center;padding-top:4px'>Cloudflare AI · Gratis</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")
c_in, c_btn, c_clr = st.columns([6, 1, 1])
with c_in:
    user_input = st.text_input("", placeholder="🤖 Tanya AI tentang data...", label_visibility="collapsed", key="chat_input_box")
with c_btn:
    send = st.button("➤", use_container_width=True, key="chat_send")
with c_clr:
    if st.button("🗑️", use_container_width=True, key="chat_clear"):
        st.session_state.chat_history = []
        st.rerun()

if (send or user_input) and user_input.strip():
    if send:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("AI menganalisis..."):
            try:
                answer = ask_ai(user_input, stats, sel_loc, sel_month, sel_date, df_filt)
            except Exception as e:
                answer = f"❌ Error: {str(e)}"
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center;padding:20px 0;color:#3a4a6a;font-size:.55rem'>
  NLO1 Dept · Lead Time Std Dev Dashboard · Data source: Google Sheets · Auto-refresh every 60s
</div>""", unsafe_allow_html=True)
