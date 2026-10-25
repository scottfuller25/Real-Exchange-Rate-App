"""
Real Exchange Rate Explorer (IMF data)
======================================

Streamlit app that pulls monthly CPI and exchange-rate data from the IMF
SDMX 3.0 API and computes a bilateral real exchange rate (RER).

Definitions
-----------
S(t)   = units of Country 2 currency per 1 unit of Country 1 currency
         = (Country 2 LCU per USD) / (Country 1 LCU per USD)
P1(t)  = Country 1 monthly CPI
P2(t)  = Country 2 monthly CPI
RER(t) = S(t) * P1(t) / P2(t)
RER*   = mean of RER(t) over valid months in the selected sample
Real Index(t) = 100 * RER(t) / RER*

Run with:  streamlit run app.py
"""

from __future__ import annotations

import io
import os
import re
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_URL = "https://api.imf.org/external/sdmx/3.0"
DATA_START = "1976-01"
CPI_FLOW = ("IMF.STA", "CPI")
ER_FLOW = ("IMF.STA", "ER")
CPI_KEY = "{iso}.CPI._T.IX.M"
ER_KEY = "{iso}.XDC_USD.PA_RT.M"
EURO_AREA = "G163"
USA = "USA"

ACCEPT_CSV = "application/vnd.sdmx.data+csv;version=2.0.0"
ACCEPT_JSON = "application/vnd.sdmx.data+json;version=2.0.0"
ACCEPT_STRUCT = "application/vnd.sdmx.structure+json;version=2.0.0"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

REAL_COLOR = "#4F46E5"   # indigo
NOM_COLOR = "#F59E0B"    # amber

# Common currency codes, used only to make labels friendlier.
CURRENCIES = {
    "USA": "USD", "G163": "EUR", "JPN": "JPY", "GBR": "GBP", "CHE": "CHF", "CAN": "CAD",
    "AUS": "AUD", "NZL": "NZD", "CHN": "CNY", "HKG": "HKD", "SGP": "SGD", "KOR": "KRW",
    "IND": "INR", "IDN": "IDR", "MYS": "MYR", "THA": "THB", "PHL": "PHP", "VNM": "VND",
    "MEX": "MXN", "BRA": "BRL", "ARG": "ARS", "CHL": "CLP", "COL": "COP", "PER": "PEN",
    "ZAF": "ZAR", "NGA": "NGN", "EGY": "EGP", "KEN": "KES", "TUR": "TRY", "ISR": "ILS",
    "SAU": "SAR", "ARE": "AED", "SWE": "SEK", "NOR": "NOK", "DNK": "DKK", "POL": "PLN",
    "CZE": "CZK", "HUN": "HUF", "ROU": "RON", "ISL": "ISK", "PAK": "PKR", "BGD": "BDT",
    "RUS": "RUB", "UKR": "UAH",
}

# Quick-pick pairs shown in the sidebar: label -> (Country 1, Country 2)
QUICK_PAIRS = {
    "USD → JPY": ("USA", "JPN"),
    "USD → EUR": ("USA", "G163"),
    "GBP → USD": ("GBR", "USA"),
    "USD → CNY": ("USA", "CHN"),
    "USD → MXN": ("USA", "MEX"),
    "EUR → CHF": ("G163", "CHE"),
}

PERIOD_PRESETS = ["Full history", "Since 2000", "Last 20y", "Last 10y", "Last 5y"]


# --------------------------------------------------------------------------
# Styling
# --------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }

.hero { margin-bottom: 1.4rem; }
.hero .eyebrow {
    font-size: .78rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
    color: #6366F1; margin-bottom: .35rem;
}
.hero h1 {
    font-size: 2.15rem; font-weight: 700; letter-spacing: -.02em; line-height: 1.15; margin: 0;
    padding: 0;
}
.hero p { opacity: .72; font-size: 1.02rem; margin-top: .5rem; max-width: 760px; }

.pair-chip {
    display: inline-flex; align-items: center; gap: .55rem; padding: .45rem .9rem;
    border-radius: 999px; border: 1px solid rgba(99,102,241,.35);
    background: rgba(99,102,241,.08); font-weight: 600; font-size: .95rem;
}
.pair-chip span.sep { opacity: .5; font-weight: 400; }

.kpi {
    border: 1px solid rgba(128,128,128,.22); border-radius: 16px; padding: 1rem 1.15rem;
    background: rgba(128,128,128,.04); height: 100%;
    transition: border-color .2s ease, transform .2s ease;
}
.kpi:hover { border-color: rgba(99,102,241,.5); transform: translateY(-1px); }
.kpi .label { font-size: .78rem; font-weight: 500; opacity: .65; text-transform: uppercase;
    letter-spacing: .05em; }
.kpi .value { font-size: 1.65rem; font-weight: 700; letter-spacing: -.01em; margin-top: .25rem; }
.kpi .sub { font-size: .82rem; opacity: .65; margin-top: .15rem; }
.kpi .up { color: #10B981; font-weight: 600; }
.kpi .down { color: #EF4444; font-weight: 600; }

.insight {
    border-left: 4px solid #6366F1; border-radius: 10px; padding: .85rem 1.1rem;
    background: rgba(99,102,241,.07); margin: 1.1rem 0 .4rem 0; font-size: .98rem;
}

.step { font-size: .8rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
    opacity: .6; margin: 1.1rem 0 .3rem 0; }

[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.15); }
[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

.stButton > button, .stDownloadButton > button {
    border-radius: 10px; font-weight: 600; transition: all .15s ease;
}
.stDownloadButton > button {
    background: #4F46E5; color: white; border: none; padding: .55rem 1.2rem;
}
.stDownloadButton > button:hover { background: #4338CA; color: white; }

.stTabs [data-baseweb="tab-list"] { gap: .25rem; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: .5rem 1rem; }
</style>
"""


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------
def _headers(accept: str) -> dict:
    headers = {
        "Accept": accept,
        "User-Agent": "Mozilla/5.0 (RER-Explorer; Python requests)",
        "Cache-Control": "no-cache",
    }
    key = os.environ.get("IMF_API_KEY")  # optional subscription key
    if key:
        headers["Ocp-Apim-Subscription-Key"] = key
    return headers


def _get(url: str, accept: str, params: dict | None = None) -> requests.Response | None:
    """GET with simple retry/backoff. Returns None for 404/no-data responses."""
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=_headers(accept), params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (404, 204):
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"IMF API request failed: {url} ({last_err})")


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
_PERIOD_PATTERNS = [
    re.compile(r"^(\d{4})-?M(\d{1,2})$"),               # 2024-M01, 2024M01
    re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$"),    # 2024-01, 2024-01-01
]


def parse_period(value) -> pd.Timestamp | None:
    """Convert IMF monthly TIME_PERIOD strings to a month-start Timestamp."""
    s = str(value).strip()
    for pat in _PERIOD_PATTERNS:
        m = pat.match(s)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12:
                return pd.Timestamp(year=year, month=month, day=1)
    return None


def _to_series(periods, values) -> pd.Series:
    dates = [parse_period(p) for p in periods]
    ser = pd.Series(pd.to_numeric(pd.Series(list(values)), errors="coerce").values, index=dates)
    ser = ser[ser.index.notna()]
    ser = ser[~ser.index.duplicated(keep="last")].sort_index()
    ser = ser.replace([np.inf, -np.inf], np.nan).dropna()
    ser.index = pd.DatetimeIndex(ser.index)
    return ser


def parse_sdmx_csv(text: str) -> pd.Series:
    if not text or not text.strip():
        return pd.Series(dtype=float)
    df = pd.read_csv(io.StringIO(text), dtype=str)
    cols = {c.upper(): c for c in df.columns}
    if "TIME_PERIOD" not in cols or "OBS_VALUE" not in cols:
        return pd.Series(dtype=float)
    return _to_series(df[cols["TIME_PERIOD"]], df[cols["OBS_VALUE"]])


def parse_sdmx_json(payload: dict) -> pd.Series:
    """Parse SDMX-JSON (2.0 / 1.0 style) data messages."""
    data = payload.get("data", payload)
    datasets = data.get("dataSets") or []
    structure = data.get("structure") or (data.get("structures") or [{}])[0]
    obs_dims = (structure.get("dimensions") or {}).get("observation") or []
    if not datasets or not obs_dims:
        return pd.Series(dtype=float)
    time_values = [v.get("value", v.get("id")) for v in obs_dims[0].get("values", [])]

    periods, values = [], []
    for ds in datasets:
        for series in (ds.get("series") or {}).values():
            for idx, obs in (series.get("observations") or {}).items():
                i = int(idx.split(":")[0])
                if i < len(time_values):
                    val = obs[0] if isinstance(obs, list) and obs else obs
                    periods.append(time_values[i])
                    values.append(val)
    return _to_series(periods, values)


# --------------------------------------------------------------------------
# Data retrieval (cached)
# --------------------------------------------------------------------------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_series(agency: str, flow: str, key: str) -> tuple[pd.Series, str | None]:
    """Fetch one monthly series. Returns (series, error_message)."""
    url = f"{BASE_URL}/data/dataflow/{agency}/{flow}/+/{key}"
    errors = []
    for accept, parser in ((ACCEPT_CSV, "csv"), (ACCEPT_JSON, "json")):
        try:
            resp = _get(url, accept)
            if resp is None:
                return pd.Series(dtype=float), f"No data returned for {flow} key {key}."
            ser = parse_sdmx_csv(resp.text) if parser == "csv" else parse_sdmx_json(resp.json())
            if not ser.empty:
                return ser[ser.index >= pd.Timestamp(DATA_START)], None
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            errors.append(f"{parser}: {exc}")
    msg = "; ".join(errors) if errors else f"Empty response for {flow} key {key}."
    return pd.Series(dtype=float), msg


def get_cpi(iso: str) -> tuple[pd.Series, str | None]:
    return fetch_series(*CPI_FLOW, CPI_KEY.format(iso=iso))


def get_lcu_per_usd(iso: str) -> tuple[pd.Series, str | None]:
    """Local currency units per USD. The USA is 1 by definition."""
    if iso == USA:
        idx = pd.date_range(DATA_START, pd.Timestamp.today().normalize(), freq="MS")
        return pd.Series(1.0, index=idx), None
    return fetch_series(*ER_FLOW, ER_KEY.format(iso=iso))


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_countries() -> dict[str, str]:
    """Return {ISO3: name}. Tries the IMF codelist, falls back to pycountry."""
    countries: dict[str, str] = {}
    for agency in ("IMF", "IMF.STA"):
        try:
            resp = _get(f"{BASE_URL}/structure/codelist/{agency}/CL_COUNTRY/+", ACCEPT_STRUCT)
            if resp is None:
                continue
            payload = resp.json()
            data = payload.get("data", payload)
            for cl in data.get("codelists", []):
                for code in cl.get("codes", []):
                    cid = code.get("id", "")
                    name = code.get("name") or (code.get("names") or {}).get("en") or cid
                    if isinstance(name, dict):
                        name = name.get("en") or next(iter(name.values()), cid)
                    if re.fullmatch(r"[A-Z]{3}", cid):
                        countries[cid] = str(name)
            if len(countries) > 50:
                break
        except Exception:  # noqa: BLE001
            countries = {}
    if len(countries) < 50:
        import pycountry

        countries = {c.alpha_3: getattr(c, "common_name", c.name) for c in pycountry.countries}
        countries["UVK"] = "Kosovo"
    countries[EURO_AREA] = "Euro area"
    return dict(sorted(countries.items(), key=lambda kv: kv[1]))


# --------------------------------------------------------------------------
# Economics
# --------------------------------------------------------------------------
def build_frame(cpi1: pd.Series, cpi2: pd.Series, er1: pd.Series, er2: pd.Series) -> pd.DataFrame:
    """Align all series on a monthly index from 1976-01 and compute S and RER."""
    pieces = [s for s in (cpi1, cpi2, er1, er2) if not s.empty]
    if not pieces:
        return pd.DataFrame()
    end = max(s.index.max() for s in pieces)
    idx = pd.date_range(DATA_START, end, freq="MS")
    df = pd.DataFrame(index=idx)
    df.index.name = "month"
    df["lcu_per_usd_1"] = er1.reindex(idx)
    df["lcu_per_usd_2"] = er2.reindex(idx)
    df["P1"] = cpi1.reindex(idx)
    df["P2"] = cpi2.reindex(idx)
    # S(t): Country 2 currency per 1 unit of Country 1 currency
    df["S"] = df["lcu_per_usd_2"] / df["lcu_per_usd_1"]
    df["RER"] = df["S"] * df["P1"] / df["P2"]
    df = df.replace([np.inf, -np.inf], np.nan)
    df.loc[df["RER"] <= 0, "RER"] = np.nan
    return df


def apply_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, float, int]:
    """Restrict to [start, end], compute RER* over valid months and the Real Index."""
    w = df.loc[start:end].copy()
    valid = w["RER"].notna()
    n_valid = int(valid.sum())
    rer_star = float(w.loc[valid, "RER"].mean()) if n_valid else float("nan")
    w["valid_RER"] = valid
    w["RER_star"] = rer_star
    w["Real_Index"] = 100.0 * w["RER"] / rer_star if n_valid else np.nan
    return w, rer_star, n_valid


# --------------------------------------------------------------------------
# Presentation helpers
# --------------------------------------------------------------------------
def ccy(iso: str, names: dict[str, str]) -> str:
    return CURRENCIES.get(iso, f"{names.get(iso, iso)} currency")


def fmt_num(x: float) -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 10:
        return f"{x:,.2f}"
    if ax >= 0.01:
        return f"{x:,.4f}"
    return f"{x:.4g}"


def coverage(ser: pd.Series) -> str:
    if ser.empty:
        return "no data"
    return f"{ser.index.min():%b %Y} → {ser.index.max():%b %Y} · {len(ser):,} obs"


def kpi(label: str, value: str, sub: str = "") -> str:
    return f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div>' \
           f'<div class="sub">{sub}</div></div>'


def preset_window(preset: str, months: list[pd.Timestamp]) -> tuple[pd.Timestamp, pd.Timestamp]:
    last = months[-1]
    if preset == "Since 2000":
        target = pd.Timestamp("2000-01-01")
    elif preset.startswith("Last "):
        years = int(re.findall(r"\d+", preset)[0])
        target = last - pd.DateOffset(years=years) + pd.DateOffset(months=1)
    else:
        target = months[0]
    first = next((m for m in months if m >= target), months[0])
    return first, last


def make_chart(w: pd.DataFrame, view: str, s_unit: str) -> go.Figure:
    both = view == "Both"
    fig = make_subplots(specs=[[{"secondary_y": both}]])

    if view in ("Real", "Both"):
        fig.add_trace(
            go.Scatter(
                x=w.index, y=w["Real_Index"], name="Real Index",
                mode="lines", line=dict(color=REAL_COLOR, width=2.4, shape="spline", smoothing=0.3),
                connectgaps=False,
                hovertemplate="<b>Real Index</b> %{y:.1f}<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_hline(y=100, line=dict(color="rgba(128,128,128,.55)", dash="dash", width=1),
                      annotation_text="Sample average = 100", annotation_position="top left",
                      annotation_font=dict(size=11, color="rgba(128,128,128,.9)"))

    if view in ("Nominal", "Both"):
        fig.add_trace(
            go.Scatter(
                x=w.index, y=w["S"], name=f"Nominal rate ({s_unit})",
                mode="lines", line=dict(color=NOM_COLOR, width=2.2, shape="spline", smoothing=0.3),
                connectgaps=False,
                hovertemplate=f"<b>Nominal</b> %{{y:,.4g}} {s_unit}<extra></extra>",
            ),
            secondary_y=both,
        )

    grid = "rgba(128,128,128,.14)"
    fig.update_xaxes(showgrid=False, showline=False, ticks="", hoverformat="%b %Y",
                     rangeselector=dict(
                         buttons=[dict(count=5, label="5Y", step="year", stepmode="backward"),
                                  dict(count=10, label="10Y", step="year", stepmode="backward"),
                                  dict(count=20, label="20Y", step="year", stepmode="backward"),
                                  dict(step="all", label="All")],
                         bgcolor="rgba(128,128,128,.10)", activecolor="rgba(99,102,241,.35)",
                         font=dict(size=11), y=1.12, x=1, xanchor="right"))
    if view == "Real":
        fig.update_yaxes(title_text="Real Index (average = 100)", gridcolor=grid, zeroline=False)
    elif view == "Nominal":
        fig.update_yaxes(title_text=s_unit, gridcolor=grid, zeroline=False)
    else:
        fig.update_yaxes(title_text="Real Index (average = 100)", secondary_y=False, gridcolor=grid,
                         zeroline=False, title_font=dict(color=REAL_COLOR), tickfont=dict(color=REAL_COLOR))
        fig.update_yaxes(title_text=s_unit, secondary_y=True, showgrid=False, zeroline=False,
                         title_font=dict(color=NOM_COLOR), tickfont=dict(color=NOM_COLOR))

    fig.update_layout(
        height=500, hovermode="x unified", margin=dict(l=8, r=8, t=56, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font=dict(family="Inter, system-ui, sans-serif")),
    )
    return fig


# --------------------------------------------------------------------------
# Sidebar callbacks
# --------------------------------------------------------------------------
def _swap() -> None:
    st.session_state.iso1, st.session_state.iso2 = st.session_state.iso2, st.session_state.iso1


def _set_pair(pair_label: str) -> None:
    a, b = QUICK_PAIRS[pair_label]
    st.session_state.iso1, st.session_state.iso2 = a, b


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="💱", layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    with st.spinner("Loading country list…"):
        countries = load_countries()
    codes = list(countries.keys())
    st.session_state.setdefault("iso1", USA if USA in codes else codes[0])
    st.session_state.setdefault("iso2", "JPN" if "JPN" in codes else codes[1])

    def label(code: str) -> str:
        cur = CURRENCIES.get(code)
        return f"{countries.get(code, code)} · {cur}" if cur else f"{countries.get(code, code)} ({code})"

    # ---------------- Sidebar ----------------
    with st.sidebar:
        st.markdown("### 💱 Setup")

        st.markdown('<div class="step">① Choose a currency pair</div>', unsafe_allow_html=True)
        st.caption("Popular pairs")
        qcols = st.columns(3)
        for i, pl in enumerate(QUICK_PAIRS):
            qcols[i % 3].button(pl, key=f"q_{i}", on_click=_set_pair, args=(pl,), width="stretch")

        st.selectbox("Country 1 (base currency)", codes, key="iso1", format_func=label,
                     help="S(t) is quoted per 1 unit of this country's currency. Type to search.")
        st.button("⇅  Swap countries", on_click=_swap, width="stretch")
        st.selectbox("Country 2 (quote currency)", codes, key="iso2", format_func=label,
                     help="S(t) is expressed in this country's currency. Type to search.")

    iso1, iso2 = st.session_state.iso1, st.session_state.iso2
    name1, name2 = countries.get(iso1, iso1), countries.get(iso2, iso2)
    c1_ccy, c2_ccy = ccy(iso1, countries), ccy(iso2, countries)
    s_unit = f"{c2_ccy} per {c1_ccy}" if iso1 in CURRENCIES and iso2 in CURRENCIES \
        else f"{c2_ccy} per 1 {c1_ccy}"

    # ---------------- Header ----------------
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">IMF data · Monthly since 1976</div>
          <h1>Real Exchange Rate Explorer</h1>
          <p>See how much a currency has really moved once inflation in both countries is
          taken into account, and compare it with the plain market exchange rate.</p>
        </div>
        <div class="pair-chip">{name1} <span class="sep">→</span> {name2}
          <span class="sep">·</span> <span style="font-weight:500;opacity:.8">{s_unit}</span></div>
        """,
        unsafe_allow_html=True,
    )

    if iso1 == iso2:
        st.warning("Pick two different countries to compare.", icon="⚠️")
        st.stop()

    with st.status(f"Fetching IMF data for {name1} and {name2}…", expanded=False) as status:
        cpi1, e_cpi1 = get_cpi(iso1)
        cpi2, e_cpi2 = get_cpi(iso2)
        er1, e_er1 = get_lcu_per_usd(iso1)
        er2, e_er2 = get_lcu_per_usd(iso2)
        status.update(label="IMF data loaded", state="complete")

    missing = [n for n, s in ((f"CPI for {name1}", cpi1), (f"CPI for {name2}", cpi2),
                              (f"exchange rate for {name1}", er1), (f"exchange rate for {name2}", er2))
               if s.empty]
    if missing:
        st.error(
            "The IMF doesn't have monthly data for: **" + ", ".join(missing) + "**.\n\n"
            "Try a different country, or use **Clear cached data** in the sidebar if you think "
            "this was a temporary connection problem.", icon="🔍")
        details = [e for e in (e_cpi1, e_cpi2, e_er1, e_er2) if e]
        if details:
            with st.expander("Technical details"):
                for e in details:
                    st.code(e, language=None)
        with st.sidebar:
            if st.button("↻  Clear cached data", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        st.stop()

    df = build_frame(cpi1, cpi2, er1, er2)
    valid_months = df.index[df["RER"].notna()]
    if len(valid_months) == 0:
        st.error("These two countries have no months where both inflation and exchange-rate "
                 "data are available.", icon="🔍")
        st.stop()
    months = list(pd.date_range(valid_months.min(), valid_months.max(), freq="MS"))
    month_opts = [m.strftime("%Y-%m") for m in months]

    # ---------------- Sidebar: period + view ----------------
    win_key = f"window_{iso1}_{iso2}"
    st.session_state.setdefault(win_key, (month_opts[0], month_opts[-1]))

    def _apply_preset() -> None:
        p = st.session_state.get(f"preset_{iso1}_{iso2}")
        if p:
            a, b = preset_window(p, months)
            st.session_state[win_key] = (a.strftime("%Y-%m"), b.strftime("%Y-%m"))

    with st.sidebar:
        st.markdown('<div class="step">② Pick the sample period</div>', unsafe_allow_html=True)
        st.pills("Quick ranges", PERIOD_PRESETS, key=f"preset_{iso1}_{iso2}",
                 on_change=_apply_preset, label_visibility="collapsed")
        picked = st.select_slider(
            "Start and end month", options=month_opts, key=win_key,
            format_func=lambda d: pd.Timestamp(d + "-01").strftime("%b %Y"),
            help="The average real exchange rate (RER*) is recalculated over this window.",
        )
        if not isinstance(picked, (tuple, list)):
            picked = (month_opts[0], month_opts[-1])
        start, end = sorted(pd.Timestamp(m + "-01") for m in picked)

        st.markdown('<div class="step">③ Choose what to plot</div>', unsafe_allow_html=True)
        view = st.segmented_control("Series", ["Real", "Nominal", "Both"], default="Both",
                                    key="view", label_visibility="collapsed") or "Both"

        st.divider()
        if st.button("↻  Clear cached data", width="stretch",
                     help="Re-download the latest data from the IMF."):
            st.cache_data.clear()
            st.rerun()

    w, rer_star, n_valid = apply_window(df, start, end)
    if n_valid == 0:
        st.error("No months with complete data in this window. Try widening the period.", icon="📅")
        st.stop()

    # ---------------- KPI cards ----------------
    real = w["Real_Index"].dropna()
    nom = w["S"].dropna()
    last_real, last_date = real.iloc[-1], real.index[-1]
    dev = last_real - 100
    nom_first, nom_last = nom.iloc[0], nom.iloc[-1]
    nom_chg = (nom_last / nom_first - 1) * 100
    total = len(w)

    st.write("")
    k1, k2, k3, k4 = st.columns(4)
    arrow = "up" if dev >= 0 else "down"
    k1.markdown(kpi(f"Real Index · {last_date:%b %Y}", f"{last_real:.1f}",
                    f'<span class="{arrow}">{dev:+.1f}%</span> vs. period average'),
                unsafe_allow_html=True)
    k2.markdown(kpi(f"Market rate · {nom.index[-1]:%b %Y}", fmt_num(nom_last), s_unit),
                unsafe_allow_html=True)
    k3.markdown(kpi("Market rate change", f"{nom_chg:+.1f}%",
                    f"{nom.index[0]:%b %Y} → {nom.index[-1]:%b %Y}"),
                unsafe_allow_html=True)
    k4.markdown(kpi("Average real rate (RER*)", fmt_num(rer_star),
                    f"{n_valid:,} of {total:,} months with data"),
                unsafe_allow_html=True)

    # ---------------- Insight ----------------
    strength = "stronger" if dev >= 0 else "weaker"
    st.markdown(
        f'<div class="insight">💡 In <b>{last_date:%B %Y}</b>, the {c1_ccy} was '
        f'<b>{abs(dev):.1f}% {strength}</b> against the {c2_ccy} in real (inflation-adjusted) terms '
        f'than its {start:%b %Y}–{end:%b %Y} average. Over the same period the market exchange '
        f'rate moved <b>{nom_chg:+.1f}%</b>.</div>',
        unsafe_allow_html=True,
    )

    # ---------------- Tabs ----------------
    tab_chart, tab_data, tab_method = st.tabs(["📈  Chart", "🗂  Data & download", "ℹ️  How it works"])

    with tab_chart:
        st.plotly_chart(make_chart(w, view, s_unit), width="stretch",
                        config={"displaylogo": False,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]})
        st.caption(
            "**Real Index above 100** → the "
            f"{c1_ccy} buys more {name2} goods than usual. **Below 100** → it buys less. "
            f"The nominal rate is shown in actual units ({s_unit}) and is not rescaled. "
            "Drag on the chart to zoom; double-click to reset."
        )
        gaps = total - n_valid
        if gaps:
            st.info(f"{gaps} month(s) in this window are missing CPI or exchange-rate data. They "
                    "show as gaps and are left out of the average.", icon="ℹ️")

    out = w.reset_index()
    out["month"] = out["month"].dt.strftime("%Y-%m")
    out.insert(1, "country1", iso1)
    out.insert(2, "country2", iso2)
    out = out.rename(columns={
        "lcu_per_usd_1": f"{iso1}_LCU_per_USD",
        "lcu_per_usd_2": f"{iso2}_LCU_per_USD",
        "P1": f"P1_CPI_{iso1}",
        "P2": f"P2_CPI_{iso2}",
        "S": f"S_{iso2}_per_{iso1}",
    })

    with tab_data:
        top_l, top_r = st.columns([3, 1])
        top_l.markdown(f"**{total:,} monthly observations** · {start:%b %Y} to {end:%b %Y}")
        top_r.download_button(
            "⬇  Download CSV", data=out.to_csv(index=False).encode("utf-8"),
            file_name=f"rer_{iso1}_{iso2}_{start:%Y%m}_{end:%Y%m}.csv", mime="text/csv",
            width="stretch",
        )
        num_cfg = st.column_config.NumberColumn(format="%.4f")
        st.dataframe(
            out, width="stretch", hide_index=True, height=440,
            column_config={
                "month": st.column_config.TextColumn("Month"),
                "valid_RER": st.column_config.CheckboxColumn("Valid month"),
                "Real_Index": st.column_config.NumberColumn("Real Index", format="%.2f"),
                **{c: num_cfg for c in out.columns
                   if c not in ("month", "country1", "country2", "valid_RER", "Real_Index")},
            },
        )
        with st.expander("Data coverage by series"):
            st.markdown(
                f"| Series | IMF key | Coverage |\n|---|---|---|\n"
                f"| CPI · {name1} | `{CPI_KEY.format(iso=iso1)}` | {coverage(cpi1)} |\n"
                f"| CPI · {name2} | `{CPI_KEY.format(iso=iso2)}` | {coverage(cpi2)} |\n"
                f"| {name1} per USD | `{ER_KEY.format(iso=iso1)}` | "
                f"{'1.0 by definition' if iso1 == USA else coverage(er1)} |\n"
                f"| {name2} per USD | `{ER_KEY.format(iso=iso2)}` | "
                f"{'1.0 by definition' if iso2 == USA else coverage(er2)} |"
            )

    with tab_method:
        st.markdown("#### What the app calculates")
        m1, m2 = st.columns(2)
        with m1:
            st.markdown("**Nominal exchange rate** — units of Country 2 currency per 1 unit of "
                        "Country 1 currency, built from IMF rates quoted against the US dollar:")
            st.latex(r"S_t = \frac{E_{2,t}\ (\text{LCU}_2/\text{USD})}{E_{1,t}\ (\text{LCU}_1/\text{USD})}")
            st.markdown("**Real exchange rate** — adjusts for each country's consumer prices:")
            st.latex(r"RER_t = S_t \times \frac{P_{1,t}}{P_{2,t}}")
        with m2:
            st.markdown("**Benchmark** — the average real rate over the months you select:")
            st.latex(r"RER^{*} = \frac{1}{N}\sum_{t \in \text{valid}} RER_t")
            st.markdown("**Real Index** — 100 means \"at its average level\":")
            st.latex(r"\text{Real Index}_t = 100 \times \frac{RER_t}{RER^{*}}")
        st.markdown(
            "- A month is **valid** only when both CPIs and both exchange rates are available.\n"
            "- CPI base years differ by country; this doesn't matter because the index is "
            "rescaled to its own average.\n"
            "- The Euro area (code G163) has exchange-rate data from 1999 onward.\n"
            "- Source: IMF SDMX 3.0 API (`api.imf.org`), datasets CPI and ER."
        )


if __name__ == "__main__":
    main()
