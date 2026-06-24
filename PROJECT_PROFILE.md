# SmartFinance Dashboard — Project Profile
**Reproducibility, Reusability & Governance Reference**

This document is the "read me and understand" companion to the codebase — it exists so that you (or anyone else who picks this project up in six months) can reproduce the environment exactly, understand why each design decision was made, and know what's been validated versus what's still an assumption. It reflects the actual current state of the code, not the original design — several things changed shape during hands-on testing, and that history is preserved below rather than hidden.

---

## 1. What This Project Is

SmartFinance is a Streamlit dashboard for Nigerian SMEs that turns a transaction Excel file into: KPIs, a composite health score, a rule-based financial copilot, a 3-month cashflow forecast, and two report formats (PDF narrative, Excel workbook). It's the SME-facing product layer of the broader QuantScore Analytics venture.

**Target user:** a small business owner with little to no formal bookkeeping, uploading a spreadsheet of revenue/expense transactions and expecting plain-English answers, not a BI tool.

---

## 2. Module Map

| File | Responsibility | Depends on |
|---|---|---|
| `app.py` | Streamlit entry point — page routing, sidebar, theme CSS, all 7 pages | everything below |
| `data_loader.py` | Reads the Excel file, normalizes headers/Type/Amount, surfaces (not hides) data-quality warnings | `pandas`, `streamlit` |
| `cleaner.py` | Final tidy-up after `data_loader` — drops rows that failed normalization, fills missing Category/Description, sorts | `pandas` |
| `analytics.py` | `FinanceAnalytics` class — every KPI, trend, and breakdown calculation lives here. 26 public methods. | `pandas` |
| `forecasting.py` | 3-month cashflow projection (growth-rate extrapolation) + cash-shortage/runway alert | `analytics.py` |
| `insights.py` | `business_health_score()` (5-dimension weighted composite) + `generate_recommendations()` (rule-based, priority-sorted) | `analytics.py` |
| `copilot.py` | Natural-language Q&A — precise regex intents, a fuzzy backup classifier, and a smart fallback | `analytics.py` |
| `charts.py` | All Plotly figure builders (bar, line, donut, forecast chart) | `plotly` |
| `reports.py` | Two independent export paths: `generate_pdf_report()` (narrative one-pager) and `generate_summary_report()` (5-sheet Excel) | `analytics.py`, `reportlab`, fonts/ |
| `.streamlit/config.toml` | Real Streamlit theme config (dark) — see §6 for why this exists | — |
| `fonts/` | Bundled `DejaVuSans.ttf` / `DejaVuSans-Bold.ttf` — see §6 for why | — |

**Data flow:** `data_loader.load_data()` → `cleaner.clean_data()` → `FinanceAnalytics(df)` → everything else reads from that one analytics object. There's a single source of truth for every number on every page.

---

## 3. Reproducing This Environment

```bash
# 1. Clone/copy the project, then from inside the folder:
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 2. Install exact dependencies
pip install -r requirements.txt

# 3. Confirm these exist before first run — they are NOT auto-created
#    and the app will error without them:
#    smart_finance_dashboard/.streamlit/config.toml
#    smart_finance_dashboard/fonts/DejaVuSans.ttf
#    smart_finance_dashboard/fonts/DejaVuSans-Bold.ttf
#    smart_finance_dashboard/data/sample_data.xlsx

# 4. Run
streamlit run app.py
```

`requirements.txt` (current, pinned by minimum version):
```
streamlit>=1.35.0
pandas>=2.0.0
openpyxl>=3.1.0
plotly>=5.20.0
numpy>=1.26.0
xlsxwriter>=3.2.0
reportlab>=4.0.0
```

**Deployment note (Render / Streamlit Cloud):** the build will run `pip install -r requirements.txt` fresh on a Linux target — this hasn't been verified on an actual Render build yet, only in a dev sandbox. Don't assume parity with a Windows venv without a real deploy check.

---

## 4. Data Contract

**Required columns** (case- and whitespace-insensitive as of the data-quality fixes — see §7): `Date`, `Description`, `Category`, `Type`, `Amount`.

**`Type` accepted values** — exact match or synonym, case-insensitive:
- → `Revenue`: revenue, income, sales, sale, credit, earning, earnings, receipt, receipts
- → `Expense`: expense, expenses, cost, costs, spending, debit, payment, payments, outflow, outgoing
- Anything else is dropped, with a visible warning naming the unrecognized value(s) and the row count — never silently.

**`Amount`** — accepts `₦`, `$`, `NGN`, commas, and surrounding whitespace; sign is discarded and re-derived from `Type` (so an expense typed as a negative number is handled correctly, not dropped). Anything that still can't parse to a number is dropped with a visible warning.

**`Date`** — standard parse first, then a day-first retry (DD-MM-YYYY) on whatever failed, since that's the common Nigerian manual-entry convention. Still-unparseable dates are dropped with a warning.

**What's NOT in the data contract:** customer/promo/campaign-level data. Every "I don't have that data" caveat in copilot answers and recommendations is a direct consequence of this — it's a schema limitation, not a missing feature, until the schema is deliberately extended.

---

## 5. Governance: Data Handling

This is financial data for a real small business — treat it accordingly even in a pilot/demo context.

- **No persistent storage currently exists in this app.** Uploaded files live only in the Streamlit session (`st.cache_data` keyed by filename+bytes) and are not written to disk, a database, or sent anywhere outside the process. If that ever changes (e.g. adding a database, telemetry, or cloud storage), this section needs to be rewritten and the pilot consent conversation needs to reflect it accurately.
- **No API keys or secrets currently exist in this codebase.** If LLM-based copilot routing is added later (see §8), the key must go in `.streamlit/secrets.toml` (gitignored) or the hosting platform's secret manager — never hardcoded, never committed.
- **Before any real pilot data is uploaded**, be able to state plainly what happens to it. Current honest answer: "it's processed in memory for this session only and isn't stored or sent anywhere." Keep that true, or update this document and the pilot script the moment it isn't.
- **`.gitignore` should exclude:** `venv/`, `__pycache__/`, `data/` if it ever contains real (non-sample) uploaded business data, and any future `secrets.toml`.

---

## 6. Design Decisions Worth Knowing (and Why)

These aren't obvious from reading the code — each one was a deliberate choice made after hitting a real problem, not an arbitrary stylistic pick.

**Why fonts are bundled in `fonts/` instead of relying on the system:**
The base-14 PDF fonts (Helvetica, etc.) don't contain the ₦ glyph at all — it renders as nothing, not even a box, so every currency figure in the PDF report would silently appear as blank space. DejaVu Sans has the glyph. Fonts are bundled as files in the repo rather than referenced from a system path because Render/Streamlit Cloud aren't guaranteed to have DejaVu pre-installed — pointing at a system path would work in dev and break in production with no warning.

**Why `.streamlit/config.toml` exists instead of pure CSS overrides:**
The original dark theme was implemented entirely as injected CSS targeting specific Streamlit-internal class names. Those internal names aren't stable across Streamlit versions — a fix verified against one installed version didn't reproduce on a different one (this happened in practice during development; see §7). A `theme.*` config in `config.toml` is Streamlit's public, documented theming API — every native widget gets correct contrast from Streamlit itself, with no dependency on internal DOM structure.

**Why the copilot is regex + fuzzy-matching, not an LLM:**
This was an explicit, considered tradeoff, not an oversight. An LLM-backed copilot would need: an API key managed as a secret, a per-query cost and latency budget, a context-construction layer (structured analytics as JSON, not raw transactions — LLMs are unreliable at arithmetic over raw rows), and hallucination guardrails appropriate for a finance product. None of that has been built. The current architecture is two layers:
1. **Precise regex matchers** (`_is_*` methods) — fast, deterministic, win first.
2. **Fuzzy intent classifier** (`INTENT_EXAMPLES` + Jaccard word-overlap scoring) — a safety net that only runs when no precise matcher fires, catching paraphrases of known intents without needing a new regex per phrasing. Confidence floor is `0.34`; below that, it defers to the smart fallback rather than guessing wrong.

A true LLM-routing layer is a legitimate future step (see §8) but is a different cost/architecture commitment, not a drop-in upgrade.

**Why forecasting uses growth-rate extrapolation, not Moving Average/ARIMA/Prophet/GARCH:**
With ~6 months of real data, none of the heavier models outperform a simple clipped-growth-rate projection — and Prophet specifically carries real deployment risk (heavy build, `cmdstanpy` dependency, flaky on constrained hosts) for no accuracy gain at this data volume. This is deliberately deferred until a real pilot has enough history (12+ months) to justify it.

**Why `generate_pdf_report()` and `generate_summary_report()` are separate, not one configurable export:**
They serve different audiences. The PDF is something an owner hands to a partner or lender — narrative, score-led, short. The Excel workbook is for someone who wants to audit the actual numbers — five raw sheets, no narrative. Conflating them into one "report" with format options would have made both worse.

---

## 7. What's Actually Been Tested (and How)

Documented here because "looks right" and "verified" are different claims, and this project has tried to keep them distinct throughout.

| Claim | How it was verified |
|---|---|
| Copilot intents don't regress when new ones are added | Ran the full intent-matcher list against every previously-working phrasing after each change, via direct Python calls to `copilot.answer()` |
| Fuzzy classifier doesn't misfire on unrelated questions | Tested against off-topic and gibberish input; confirmed score stays below the `0.34` threshold and falls to the honest fallback |
| ₦ renders correctly in the PDF | Rendered the actual generated PDF to an image (`pdf2image`) and visually inspected it — confirmed Helvetica silently drops the glyph (blank, no error) before switching to DejaVu Sans |
| Dark theme actually applies | Ran the app with `.streamlit/config.toml` in place and read back `streamlit.config.get_option('theme.base')` etc. directly, rather than assuming the file format was correct |
| Data loader survives messy real-world input | Constructed synthetic files with currency-formatted amounts, Type synonyms, negative expense entries, mismatched header casing, and an all-garbage file — ran each through `load_data()` → `clean_data()` → full analytics/PDF/Excel/copilot pipeline. This is how the silent-data-loss bugs (currency symbols → 0, unrecognized Type → dropped rows, all-garbage → unhandled Arrow crash) were actually found, not theorized about. |
| App doesn't crash on page navigation | Streamlit's `AppTest` harness run against each page in the sidebar, checking `at.exception` is empty |

**What has NOT been tested:** an actual Render/Streamlit Cloud deployment of the current code; behavior with a genuinely large dataset (thousands of rows, multiple years); concurrent multi-user usage; any real pilot SME's actual data.

---

## 8. Deferred Decisions — Logged, Not Forgotten

Each of these came up during development and was deliberately not built yet, with a stated reason. Revisit them once pilot evidence exists, not before.

| Item | Why deferred | Re-evaluate when |
|---|---|---|
| LLM-based copilot routing | Real cost/latency/key-management commitment; current fuzzy layer covers paraphrases reasonably | Fallback rate in real pilot usage is high enough to justify the cost |
| Separate "Cost/Risk/Cash/Strategy Advisor" intents | Mostly duplicate existing intents (runway = Cash, health = Risk) under new names | A pilot reveals a genuine gap none of the current intents cover |
| Moving Average / Linear Trend / ARIMA / Prophet / GARCH forecasting | Current growth-rate model isn't beaten by these at ~6 months of data; Prophet adds deployment risk | A pilot SME has 12+ months of real history and the current forecast visibly underperforms |
| Customer/promo-level analytics | Not in the data schema at all | An SME's data actually includes that granularity and a pilot conversation surfaces the need |

---

## 9. Extending This Project — Where to Add Things

- **New copilot phrasing for an existing intent:** add a line to the relevant list in `INTENT_EXAMPLES` (`copilot.py`). No new regex needed — this is the whole point of the fuzzy layer.
- **New copilot intent entirely:** add a precise `_is_*` matcher + `_answer_*` handler, register both in the `handlers` list in `answer()`, and optionally also add an `INTENT_EXAMPLES` entry + `INTENT_HANDLER_NAMES` mapping for paraphrase coverage.
- **New analytics metric:** add a method to `FinanceAnalytics` in `analytics.py` — every other module reads through this one class, so this is the single place new numbers should be computed.
- **New report content:** PDF changes go in `generate_pdf_report()` (`reports.py`) — remember any new currency text needs the `_FONT_REGULAR`/`_FONT_BOLD` styles, not the default Reportlab fonts, or ₦ will silently vanish again.
- **New required data field:** update `REQUIRED_COLUMNS` and the synonym sets in `data_loader.py`, and update §4 of this document — the data contract is a contract precisely because code and documentation agree on it.

---

## 10. Glossary

- **SmartFinance Score** — composite 0–100 health score from 5 weighted dimensions (profit margin 25%, revenue growth 20%, expense control 20%, cash runway 20%, revenue diversification 15%). Defined in `insights.business_health_score()`.
- **Complete vs. partial month** — the current calendar month is "partial" until it ends; forecasting and month-over-month comparisons deliberately exclude partial months to avoid comparing 21 days of data against a full prior month.
- **Runway** — `estimated cash balance ÷ average monthly expense`, in months. Computed in `forecasting.cash_shortage_alert()`.
- **Revenue concentration** — the % of total revenue from the single largest category; flagged as a risk above an internal threshold in `analytics.revenue_concentration()`.
