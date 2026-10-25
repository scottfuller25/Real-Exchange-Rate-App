# Real Exchange Rate Explorer (IMF data)

A Streamlit app that retrieves monthly CPI and exchange-rate data from the IMF SDMX 3.0 API (from January 1976 where available) and computes a bilateral real exchange rate for any two IMF countries or the Euro area.

## Definitions

| Symbol | Meaning |
|---|---|
| `S(t)` | Units of **Country 2** currency per **1 unit of Country 1** currency |
| `P1(t)`, `P2(t)` | Monthly CPI of Country 1 and Country 2 |
| `RER(t)` | `S(t) × P1(t) / P2(t)` |
| `RER*` | Average of `RER(t)` over valid months in the selected start–end window |
| `Real Index(t)` | `100 × RER(t) / RER*` |

IMF exchange rates are local-currency units per USD (`E_i`), so the app converts them to the required direction:

```
S(t) = E2(t) / E1(t)      # (C2 per USD) / (C1 per USD) = C2 per C1
```

When either country is the United States, its rate is set to 1.0 (USD per USD).

A Real Index above 100 means Country 1's currency is stronger in real terms against Country 2 than its average over the selected sample.

## Features

- Pick Country 1 and Country 2 from the IMF country codelist, plus the Euro area (`G163`).
- Pick start and end months; `RER*` and the Real Index are recalculated whenever the window changes.
- Interactive Plotly chart with a **Real / Nominal / Both** selector. "Both" uses separate y-axes (Real Index on the left, nominal S on the right).
- Nominal `S(t)` is plotted in actual currency units and is never normalized.
- CSV download of every observation and calculation in the selected sample: month, both LCU-per-USD rates, P1, P2, S, RER, a validity flag, RER\*, and the Real Index.
- A coverage panel showing each series' first and last month, plus any retrieval warnings.

## Data sources (IMF SDMX 3.0)

Base URL: `https://api.imf.org/external/sdmx/3.0`

| Series | Dataflow | Key |
|---|---|---|
| CPI (all items, index, monthly) | `IMF.STA/CPI` | `{ISO3}.CPI._T.IX.M` |
| Exchange rate (LCU per USD, period average, monthly) | `IMF.STA/ER` | `{ISO3}.XDC_USD.PA_RT.M` |

Example request:
`https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/+/JPN.CPI._T.IX.M`

The app requests SDMX-CSV first and falls back to SDMX-JSON. Responses are cached for 6 hours (the country list for 24 hours). Use **Clear cached IMF data** in the sidebar to force a refresh.

If your IMF API access requires a subscription key, set it before launching:

```bash
export IMF_API_KEY=your_key_here
```

## Installation (Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

## Handling gaps and limited coverage

- All series are aligned on a common monthly calendar starting 1976-01.
- A month counts as **valid** only when S, P1 and P2 are all present and RER is positive and finite. Only valid months enter `RER*`. Invalid months appear as gaps in the chart and are flagged `valid_RER = False` in the CSV.
- The start/end selector spans the first through last valid month for the chosen pair.
- If the IMF returns no data for a country/series, the app names the missing series and stops rather than producing a misleading chart.
- The Euro area (`G163`) exchange rate begins in 1999. For individual euro-area members, the IMF may report euro-denominated rates (including back-converted history), so check the coverage panel before interpreting long samples.
- CPI base years differ across countries. This does not affect the Real Index, because it is normalized by `RER*`.
- If the IMF codelist endpoint is unavailable, the country list falls back to ISO 3166 codes (via `pycountry`). Some of those codes may have no IMF data.

## Files

- `app.py`: the Streamlit application
- `requirements.txt`: Python dependencies
- `README.md`: this file
