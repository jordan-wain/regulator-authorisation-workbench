"""UK FCA Firm Authorisation Workbench — Streamlit app (v2).

App-layer wrapper around Data Solutions dashboard 4015 that adds:
  - per-case state persistence (SQLite)
  - structured sidebar intake form (FCA application form alignment)
  - button-triggered Companies House PSC + officers lookup with candidate picker
  - automatic MLRO cross-check against fetched CH officers
  - wallet attribution, time-series, monthly trend, Sankey flow & cross-chain tiles
  - evidence-pack export (PDF/HTML) with full audit log + CH candidate-pick trail
  - audit log viewer
  - one-click demo case loader (clean / perimeter-hit / edge-case)
  - FCA branding (logo + #701B45 sidebar)
  - case rename, clear-results-per-phase, CSV export per result

Run locally:
    streamlit run streamlit_app/app.py
"""
from __future__ import annotations

import html as _htmllib
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import data as ds_data
from utils import pdf_export
from utils import queries as Q
from demo_fixtures import FIXTURES as DEMO_FIXTURES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSET_DIR = Path(__file__).resolve().parent / "assets"
FCA_LOGO_PATH = ASSET_DIR / "fca_logo.png"
FCA_PURPLE = "#701B45"
FCA_PURPLE_DARK = "#5C1538"   # ~20% darker for sidebar button contrast
FCA_PURPLE_HOVER = "#8A2455"  # slightly lighter than base for hover state

# Unified Plotly palette (#10)
FCA_PALETTE = [FCA_PURPLE, "#A85278", "#D17BA0", "#5C1538", "#3F0F2A", "#C0392B", "#E67E22"]
FCA_DIVERGING = {"approve": "#1a7f37", "warn": "#e67e22", "refuse": "#c0392b",
                 "info": FCA_PURPLE, "muted": "#888888"}

REGIMES = [
    "FCA Cryptoasset Firm (MLR Part 5A)",
    "FCA EMI (Electronic Money Institution)",
    "FCA AISP (Account Information Service Provider)",
    "FCA Principal Firm Authorisation (FSMA)",
    "FCA Stablecoin Issuer (proposed regime)",
]

CRYPTO_ACTIVITIES = [
    "Fiat-to-Crypto Exchange",
    "Crypto-to-Crypto Exchange",
    "Custodian Wallet Provider",
    "ATM Operator",
    "Multiple (see note)",
]

DECISION_OUTCOMES = [
    "Pending",
    "Approve (Standard)",
    "Approve (Enhanced supervision)",
    "Approve (Intensive supervision)",
    "Minded to refuse — issue notice",
    "Refuse",
    "Application withdrawn",
]

CUSTODY_OPTIONS = [
    "", "Self-custody", "Third-party custodian", "Hybrid",
    "Non-custodial (declared)",
]


DEFAULTS = {
    "second_reviewer": "",
    "crypto_activities": "", "declared_transaction_count": "",
    "mlro_name": "", "mlro_experience": "",
    "financial_projections_y1": "", "financial_projections_y3": "",
    "flow_of_funds_description": "", "bwra_reference": "",
    "customer_risk_methodology": "", "blockchain_monitoring_tools": "",
    "group_structure": "", "travel_rule_compliance": "",
    "outsourcing_arrangements": "",
}


# ---------------------------------------------------------------------------
# Demo cases (#6)
# ---------------------------------------------------------------------------

DEMO_CASES = {
    "🟢 Coinbase (clean licensed)": {
        "applicant_name": "Coinbase.com",
        "applicant_legal_entity": "CB Payments",
        "regime_applied_for": "FCA Cryptoasset Firm (MLR Part 5A)",
        "crypto_activities": ["Fiat-to-Crypto Exchange", "Custodian Wallet Provider"],
        "case_officer": "FCA-Analyst-001",
        "declared_wallets": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3, 0x503828976d22510aad0201ac7ec88293211d23da",
        "declared_territories": "United Kingdom, Ireland, EU",
        "declared_volume_usd": "50000000000",
        "reconciliation_window_days": 90,
        "declared_user_count": "100000000",
        "declared_balance_usd": "5000000000",
        "declared_assets": "BTC, ETH, USDC, USDT, SOL",
        "declared_transaction_count": "250000000",
        "declared_business_model": "Centralised exchange and custodian wallet provider",
        "declared_custody_arrangement": "Self-custody",
        "declared_ubos": "Brian Armstrong, Fred Ehrsam (founders)",
        "declared_peer_cohort": "Kraken, Bitstamp.net, Gemini",
        "mlro_name": "Catriona Hardman",
        "bwra_reference": "BWRA-2024-Q4",
        "customer_risk_methodology": "Risk-tiering by jurisdiction + product use + customer KYC level",
        "blockchain_monitoring_tools": "Chainalysis KYT, Reactor",
        "travel_rule_compliance": "Part 7A MLR compliant — TRP integration via Notabene",
        "prior_denials_yn": "No",
    },
    "🛑 BitBargain.co.uk (perimeter hit)": {
        "applicant_name": "BitBargain.co.uk",
        "applicant_legal_entity": "BitBargain Ltd",
        "regime_applied_for": "FCA Cryptoasset Firm (MLR Part 5A)",
        "crypto_activities": ["Fiat-to-Crypto Exchange"],
        "case_officer": "FCA-Analyst-002",
        "declared_wallets": "",
        "declared_territories": "United Kingdom",
        "declared_volume_usd": "10000000",
        "reconciliation_window_days": 90,
        "declared_user_count": "5000",
        "declared_balance_usd": "500000",
        "declared_assets": "BTC",
        "declared_transaction_count": "20000",
        "declared_business_model": "Peer-to-peer fiat-to-crypto exchange",
        "declared_custody_arrangement": "Non-custodial (declared)",
        "declared_ubos": "(undeclared)",
        "declared_peer_cohort": "LocalBitcoins, Hodl Hodl, Bisq",
        "mlro_name": "(awaiting)",
        "bwra_reference": "",
        "blockchain_monitoring_tools": "(none declared)",
        "prior_denials_yn": "No",
    },
    "🟡 Binance.je (edge case)": {
        "applicant_name": "Binance.je",
        "applicant_legal_entity": "Binance Jersey Ltd",
        "regime_applied_for": "FCA Cryptoasset Firm (MLR Part 5A)",
        "crypto_activities": ["Fiat-to-Crypto Exchange", "Crypto-to-Crypto Exchange"],
        "case_officer": "FCA-Analyst-003",
        "declared_wallets": "",
        "declared_territories": "Jersey, United Kingdom (passporting)",
        "declared_volume_usd": "1000000000",
        "reconciliation_window_days": 90,
        "declared_user_count": "500000",
        "declared_balance_usd": "100000000",
        "declared_assets": "BTC, ETH, BNB",
        "declared_transaction_count": "5000000",
        "declared_business_model": "Cryptoasset exchange — Jersey-domiciled, UK-passporting",
        "declared_custody_arrangement": "Hybrid",
        "declared_ubos": "Changpeng Zhao (CZ)",
        "declared_peer_cohort": "Coinbase, Kraken, Bitstamp.net",
        "mlro_name": "(to be confirmed)",
        "bwra_reference": "BWRA-2024-Q3",
        "group_structure": "Subsidiary of Binance Holdings Ltd (Cayman); shares operational infrastructure with Binance.com",
        "blockchain_monitoring_tools": "Chainalysis KYT",
        "prior_denials_yn": "Yes",
        "prior_denial_detail": "Ontario Securities Commission cease-trade order, 2021. FCA consumer warning, 2021 (since lifted for Binance Jersey).",
    },
}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _h(s) -> str:
    """HTML-escape None-safe (#G — used in any unsafe_allow_html block)."""
    return _htmllib.escape(str(s)) if s is not None else ""


def _empty_state() -> dict:
    return {
        "intake": {},
        "phase0": {}, "phase1": {}, "phase2": {}, "phase3": {}, "phase4": {},
        "phase5": {}, "phase6": {}, "phase7": {}, "phase8": {}, "phase9": {},
    }


def _seed_summary_fields_from_fixtures(demo_pick: str) -> None:
    """Populate the headline state fields that the Case Summary tab reads,
    based on the loaded fixture pack. Without these the rollup section
    looks empty even though all the per-phase tiles are filled.
    """
    pack = DEMO_FIXTURES.get(demo_pick) or {}
    state = st.session_state["state"]
    # Phase 0 perimeter / risk-tier / sanctions / FCA warning summary fields
    p0 = state.setdefault("phase0", {})
    perim_rows = pack.get("phase0", {}).get("perimeter", {}).get("records") or []
    if perim_rows:
        p0["perimeter_status"] = perim_rows[0].get("Perimeter Status")
        p0["register_status"]  = perim_rows[0].get("Register Status")
    rt_rows = pack.get("phase0", {}).get("risk_tier", {}).get("records") or []
    if rt_rows:
        p0["risk_tier"] = rt_rows[0].get("Risk Tier")
    sanc = pack.get("phase0", {}).get("sanctions", {}).get("records") or []
    if sanc:
        p0["sanctions_severe_hits"] = sum(1 for r in sanc if (r.get("Severity") or "").lower() == "severe")
    # FCA warning match is computed live from check_fca_warnings — leave alone

    # Phase 5 illicit summary
    p5 = state.setdefault("phase5", {})
    illicit = pack.get("phase5", {}).get("illicit", {}).get("records") or []
    if illicit:
        try:
            p5["illicit_total_usd"] = float(sum(r.get("USD (in + out, 90d)") or 0 for r in illicit))
        except (TypeError, ValueError):
            p5["illicit_total_usd"] = 0
        p5["severe_categories"] = [
            r.get("Category") for r in illicit
            if "SEVERE" in (r.get("Severity Tier") or "")
        ]


def init_session() -> None:
    st.session_state.setdefault("case_id", "")
    st.session_state.setdefault("applicant_name", "")
    st.session_state.setdefault("state", _empty_state())


def commit() -> None:
    cid = st.session_state.get("case_id") or "UK-DRAFT"
    name = st.session_state.get("applicant_name") or "Unnamed Applicant"
    ds_data.save_case(cid, name, st.session_state["state"])


# ---------------------------------------------------------------------------
# Result-cache helpers
# ---------------------------------------------------------------------------

def save_result(phase: str, key: str, df: pd.DataFrame, label: str | None = None) -> None:
    bucket = st.session_state["state"].setdefault(phase, {}).setdefault("_results", {})
    bucket[key] = {
        "label": label or key,
        "records": df.to_dict(orient="records"),
        "columns": list(df.columns),
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    commit()


def load_result_df(phase: str, key: str) -> tuple[pd.DataFrame | None, str | None]:
    bucket = st.session_state["state"].get(phase, {}).get("_results", {})
    saved = bucket.get(key)
    if not saved:
        return None, None
    df = pd.DataFrame(saved["records"], columns=saved.get("columns"))
    return df, saved.get("ran_at")


def clear_phase_results(phase: str) -> None:
    st.session_state["state"].get(phase, {}).pop("_results", None)
    commit()


def run_query(
    sql: str,
    label: str,
    est_seconds: int = 10,
    async_: bool = False,
    max_wait: int = 600,
) -> pd.DataFrame:
    """Run a DS query with progress UI + graceful error handling.

    ``async_=True`` switches to the async endpoint, which polls every ~3s up
    to ``max_wait`` seconds. Use it for queries that scan transfer-level
    tables or otherwise exceed the ~120s synchronous limit.
    """
    try:
        mode = "async, polling" if async_ else f"sync, ~{est_seconds}s"
        with st.status(f"Running **{label}** ({mode}) against Data Solutions…",
                       expanded=False) as status:
            t0 = datetime.now(timezone.utc)
            if async_:
                def _progress(elapsed, state):
                    status.update(
                        label=f"⏳ **{label}** — {state}, {int(elapsed)}s elapsed (max {max_wait}s)…",
                        state="running",
                    )
                df = ds_data.run_ds_query_async(sql, max_wait=max_wait,
                                                progress_cb=_progress)
            else:
                df = ds_data.run_ds_query(sql)
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            status.update(label=f"✅ **{label}** — {len(df)} row(s) in {elapsed:.1f}s",
                          state="complete")
            return df
    except ds_data.DataSolutionsError as e:
        st.error(f"Data Solutions query failed for **{label}**: {e}")
        return pd.DataFrame()
    except Exception as e:  # noqa: BLE001 — last-ditch so a tab survives any failure
        st.error(f"Unexpected error running **{label}**: {type(e).__name__}: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Formatting + status colouring (#8, #9-light, #11)
# ---------------------------------------------------------------------------

def _friendly_ts(iso) -> str:
    """Render an ISO UTC timestamp as 'Last run: 2 min ago' or 'Last run: 2026-05-26 14:42 (local)'."""
    if not iso:
        return "Not run yet"
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return f"Last run: {iso}"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (now - dt).total_seconds()
    if delta < 60:
        return "Last run: just now"
    if delta < 3600:
        return f"Last run: {int(delta // 60)} min ago"
    if delta < 86400:
        return f"Last run: {int(delta // 3600)} hr ago"
    local = dt.astimezone()
    return f"Last run: {local.strftime('%Y-%m-%d %H:%M')} (local)"


def fmt_usd(value) -> str:
    """Pretty-print USD value: $5.0 B / $1.2 M / $123,456."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e12: return f"{sign}${v/1e12:.2f} T"
    if v >= 1e9:  return f"{sign}${v/1e9:.2f} B"
    if v >= 1e6:  return f"{sign}${v/1e6:.2f} M"
    if v >= 1e3:  return f"{sign}${v/1e3:.1f} K"
    return f"{sign}${v:,.0f}"


def _status_to_color(value) -> str:
    """Map emoji-prefixed status strings to subtle background colors."""
    if not isinstance(value, str):
        return ""
    s = value
    if s.startswith(("🛑", "🚨", "🔴")):    return "background-color: #fde7e7;"
    if s.startswith(("⚠️", "🟠")):          return "background-color: #fff3e0;"
    if s.startswith(("🟡", "📥")):          return "background-color: #fffbe6;"
    if s.startswith(("✅", "🟢")):          return "background-color: #e6f5e8;"
    return ""


def styled_dataframe(df: pd.DataFrame, status_cols: list[str] | None = None) -> None:
    """Render df with conditional row-cell colouring on status_cols, plus
    per-column number formatting:
      - 'USD' / 'Balance' columns → '$25.6 M' style (via fmt_usd)
      - integer-only columns like '... Days' / 'Count' / 'Findings' → '1,234'
      - Pandas datetime columns → 'YYYY-MM-DD'
      - everything else → unchanged
    """
    if df.empty:
        st.dataframe(df, use_container_width=True)
        return
    if not status_cols:
        # Auto-detect: any column whose name contains 'Status', 'Verdict',
        # 'Tier', 'Result' or 'Signal'
        auto = [c for c in df.columns
                if any(k in c for k in ("Status", "Verdict", "Tier", "Result", "Signal", "Severity", "Delta", "Maturity"))]
        status_cols = auto

    # Build a per-column formatter dict for df.style.format
    formatters: dict[str, object] = {}
    for col in df.columns:
        col_l = col.lower()
        # USD / monetary columns get compact USD format
        if "usd" in col_l or "balance" in col_l:
            formatters[col] = lambda v: fmt_usd(v) if pd.notna(v) else "—"
        # Day-counts / record-counts / findings → integer with commas
        elif any(k in col for k in ("Days", "Count", "Findings", "Tx", "N (")):
            def _int_fmt(v):
                if pd.isna(v):
                    return "—"
                try:
                    return f"{int(round(float(v))):,}"
                except (TypeError, ValueError):
                    return str(v)
            formatters[col] = _int_fmt
        # Percentages
        elif col.endswith("%") or "Delta %" in col:
            def _pct(v):
                if pd.isna(v):
                    return "—"
                try:
                    return f"{float(v):.1f}%"
                except (TypeError, ValueError):
                    return str(v)
            formatters[col] = _pct

    styler = df.style
    if formatters:
        styler = styler.format(formatters, na_rep="—")
    if status_cols:
        styler = styler.map(_status_to_color,
                            subset=[c for c in status_cols if c in df.columns])
    st.dataframe(styler, use_container_width=True)


def render_saved(
    phase: str,
    key: str,
    *,
    empty_msg: str = "Not run yet for this case.",
    explain_empty: str | None = None,
    csv_button: bool = True,
) -> pd.DataFrame | None:
    """Render a saved result (#9 status colour + #11 better empty + #24 CSV)."""
    df, ran_at = load_result_df(phase, key)
    if df is None:
        st.caption(f"_{empty_msg}_")
        return None
    if df.empty:
        msg = f"Query returned no rows (last run: {ran_at})."
        if explain_empty:
            msg += f"\n\n_{explain_empty}_"
        st.info(msg)
        return df
    st.caption(f"_{_friendly_ts(ran_at)}_")
    styled_dataframe(df)
    if csv_button:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            f"⬇️ Export `{key}` as CSV",
            data=csv,
            file_name=f"{st.session_state['case_id']}_{phase}_{key}.csv",
            mime="text/csv",
            key=f"csv_{phase}_{key}",
        )
    return df


# ---------------------------------------------------------------------------
# Reactor / KYT cross-links (G) — surface on named-counterparty tables in
# Phase 3 + Phase 5. Pure markdown links; opens in new tabs.
#
# URL patterns are best-guess based on the current shape of the consumer
# apps. If they change, swap REACTOR_SEARCH_URL / KYT_SEARCH_URL below.
# ---------------------------------------------------------------------------

from urllib.parse import quote as _urlquote  # noqa: E402

REACTOR_SEARCH_URL = "https://reactor.chainalysis.com/search?q={q}"
KYT_SEARCH_URL     = "https://kyt.chainalysis.com/alerts?search={q}"


def render_counterparty_crosslinks(phase: str, key: str, counterparty_col: str = "Counterparty",
                                    top_n: int = 10) -> None:
    """If a saved result has a ``counterparty_col``, render an expander with
    per-counterparty Reactor + KYT search links.

    The links are deliberately external — clicking opens the relevant
    Chainalysis app in a new tab, pre-filtered to that entity name. Sells
    the cross-product story: the workbench surfaces the question, Reactor
    and KYT answer the follow-up.
    """
    df, _ = load_result_df(phase, key)
    if df is None or df.empty or counterparty_col not in df.columns:
        return
    names = df[counterparty_col].dropna().astype(str).tolist()[:top_n]
    if not names:
        return
    with st.expander(f"🔗 Open these counterparties in Reactor / KYT ({len(names)})",
                     expanded=False):
        st.caption(
            "External links — open in a new tab. These take the counterparty "
            "name to the relevant Chainalysis app for deeper investigation."
        )
        for n in names:
            q = _urlquote(n)
            reactor = REACTOR_SEARCH_URL.format(q=q)
            kyt = KYT_SEARCH_URL.format(q=q)
            st.markdown(
                f"- **{n}** &nbsp;·&nbsp; "
                f"[Reactor ↗]({reactor}) &nbsp;·&nbsp; [KYT ↗]({kyt})"
            )


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def apply_styles() -> None:
    css = f"""
    <style>
      /* --- Sidebar: purple background --- */
      section[data-testid="stSidebar"] > div {{
        background-color: {FCA_PURPLE};
      }}
      section[data-testid="stSidebar"] h1,
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3,
      section[data-testid="stSidebar"] h4,
      section[data-testid="stSidebar"] p,
      section[data-testid="stSidebar"] label,
      section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
      section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color: #ffffff !important;
      }}
      section[data-testid="stSidebar"] strong,
      section[data-testid="stSidebar"] code {{
        color: #ffffff !important;
      }}
      section[data-testid="stSidebar"] code {{
        background-color: rgba(255,255,255,0.15);
        padding: 0 4px;
        border-radius: 3px;
      }}
      section[data-testid="stSidebar"] button[kind="secondaryFormSubmit"],
      section[data-testid="stSidebar"] .stButton button {{
        background-color: {FCA_PURPLE_DARK};
        color: #ffffff;
        border: 1px solid {FCA_PURPLE_DARK};
        font-weight: 600;
      }}
      section[data-testid="stSidebar"] button p,
      section[data-testid="stSidebar"] button span,
      section[data-testid="stSidebar"] button div {{
        color: #ffffff !important;
      }}
      section[data-testid="stSidebar"] .stButton button:hover {{
        background-color: {FCA_PURPLE_HOVER};
        color: #ffffff;
        border-color: {FCA_PURPLE_HOVER};
      }}
      section[data-testid="stSidebar"] .stButton button:hover p,
      section[data-testid="stSidebar"] .stButton button:hover span,
      section[data-testid="stSidebar"] .stButton button:hover div {{
        color: #ffffff !important;
      }}
      /* --- Main pane --- */
      .main h1, .main h2, .main h3 {{ color: {FCA_PURPLE}; }}
      /* #4 — section dividers: give every subheader a quiet purple left rail
         + extra top space so phase tabs feel rhythmic rather than wall-of-text */
      .main h3 {{
        border-left: 4px solid {FCA_PURPLE};
        padding-left: 0.7rem;
        margin-top: 2rem !important;
        margin-bottom: 0.6rem;
        font-size: 1.15rem;
      }}
      /* h2 (st.header) gets a thicker rail to anchor each phase */
      .main h2 {{
        border-bottom: 2px solid {FCA_PURPLE};
        padding-bottom: 0.4rem;
        margin-bottom: 1.2rem;
      }}
      /* #2 — st.metric accent: thin purple border, soft tint, FCA label colour */
      [data-testid="stMetric"] {{
        background: #faf6f8;
        border: 1px solid #e3d3dc;
        border-left: 4px solid {FCA_PURPLE};
        border-radius: 4px;
        padding: 0.6rem 0.9rem;
      }}
      [data-testid="stMetricLabel"] {{
        color: {FCA_PURPLE} !important;
        font-weight: 600;
        font-size: 0.78rem !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      [data-testid="stMetricValue"] {{
        color: #1a1a1a;
        font-weight: 600;
      }}
      /* #7 — dataframe styling: thinner border, FCA-toned header */
      [data-testid="stDataFrame"] {{
        border: 1px solid #e3d3dc;
        border-radius: 4px;
      }}
      [data-testid="stDataFrame"] thead th {{
        background: #faf6f8 !important;
        color: {FCA_PURPLE} !important;
        font-weight: 600 !important;
        text-transform: none !important;
        font-size: 0.85rem !important;
        border-bottom: 2px solid {FCA_PURPLE} !important;
      }}
      .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
        color: {FCA_PURPLE} !important;
      }}
      .stTabs [data-baseweb="tab-highlight"] {{
        background-color: {FCA_PURPLE} !important;
      }}
      /* Decision card */
      .decision-card {{
        border: 2px solid {FCA_PURPLE};
        border-radius: 8px;
        padding: 1.1rem 1.4rem;
        background: linear-gradient(180deg, #fdf7fa 0%, #f9eef3 100%);
        margin-bottom: 1.2rem;
        box-shadow: 0 2px 4px rgba(112, 27, 69, 0.08);
      }}
      .decision-card p {{
        margin: 0.35rem 0;
        line-height: 1.5;
      }}
      .decision-card strong {{
        color: {FCA_PURPLE};
        font-weight: 600;
      }}
      .decision-card h3 {{ margin-top: 0; color: {FCA_PURPLE}; }}
      .decision-card .outcome-pending {{ color: #888; font-style: italic; }}
      .decision-card .outcome-approve {{ color: #1a7f37; font-weight: 600; }}
      .decision-card .outcome-refuse  {{ color: #c0392b; font-weight: 600; }}
      .decision-card .outcome-other   {{ color: {FCA_PURPLE}; font-weight: 600; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar: case management, demo loader, intake form, rename, audit viewer
# ---------------------------------------------------------------------------

def sidebar() -> None:
    if FCA_LOGO_PATH.exists():
        st.sidebar.image(str(FCA_LOGO_PATH), use_container_width=True)
    st.sidebar.markdown("### Firm Authorisation Workbench")
    st.sidebar.caption("UK FCA — case-officer console")

    cases = ds_data.list_cases()
    options = ["➕ New case"] + [
        f"{c['case_id']} — {c['applicant_name']}" for c in cases
    ]
    pick = st.sidebar.selectbox("Case", options, key="_case_picker")

    if pick == "➕ New case":
        if st.sidebar.button("Start new case"):
            new_id = f"UK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
            st.session_state["case_id"] = new_id
            st.session_state["applicant_name"] = ""
            st.session_state["state"] = _empty_state()
            commit()
            st.rerun()
    else:
        selected_id = pick.split(" — ", 1)[0]
        if st.session_state.get("case_id") != selected_id:
            loaded = ds_data.load_case(selected_id)
            if loaded:
                st.session_state["case_id"] = loaded["case_id"]
                st.session_state["applicant_name"] = loaded["applicant_name"]
                st.session_state["state"] = loaded.get("state") or _empty_state()
                st.rerun()

    # --- Demo cases (#6) ---
    with st.sidebar.expander("🎬 Load demo case", expanded=False):
        demo_pick = st.selectbox("Pre-loaded demos", [""] + list(DEMO_CASES.keys()),
                                  key="_demo_picker")
        prepopulate = st.checkbox(
            "🎬 Demo Mode — pre-populate query results (no live DS calls)",
            value=st.session_state.get("_demo_mode", True),
            key="_demo_mode_checkbox",
            help=(
                "When on, loading a demo case also fills every phase tile with "
                "snapshot fixtures so you can walk through the app instantly. "
                "Use this for screen-recordings. Turn OFF to run real Data "
                "Solutions queries (60-180s each on a large entity like Coinbase)."
            ),
        )
        st.session_state["_demo_mode"] = prepopulate
        if demo_pick and st.button("Load demo", key="_load_demo"):
            # Sanitise: strip emoji, take first word, keep only alphanumerics
            _clean = re.sub(r'[^A-Za-z0-9]', '', demo_pick.split(' ')[1].split('.')[0]).upper()
            new_id = f"DEMO-{_clean}-{uuid.uuid4().hex[:4].upper()}"
            st.session_state["case_id"] = new_id
            st.session_state["applicant_name"] = DEMO_CASES[demo_pick]["applicant_name"]
            st.session_state["state"] = _empty_state()
            st.session_state["state"]["intake"] = dict(DEMO_CASES[demo_pick])
            # Pre-populate every phase tile with snapshot fixtures so the
            # walkthrough has no waiting on camera. The user can clear
            # them per-phase with the 🗑️ Clear results button.
            if prepopulate and demo_pick in DEMO_FIXTURES:
                for phase_key, phase_results in DEMO_FIXTURES[demo_pick].items():
                    st.session_state["state"].setdefault(phase_key, {})["_results"] = dict(phase_results)
                # Also seed the headline per-phase summary fields the Case
                # Summary tab reads (so its rollup looks coherent).
                _seed_summary_fields_from_fixtures(demo_pick)
            commit()
            ds_data.log_audit(
                new_id, "demo_loaded",
                f"{demo_pick} (prepopulated={prepopulate})",
            )
            st.rerun()

    # --- Rename case (#12) ---
    if st.session_state.get("case_id"):
        with st.sidebar.expander("✏️ Rename / re-ID case", expanded=False):
            new_cid = st.text_input("New Case ID",
                                     value=st.session_state["case_id"],
                                     key="_rename_input")
            if st.button("Apply rename", key="_rename_btn"):
                if new_cid and new_cid != st.session_state["case_id"]:
                    try:
                        ds_data.rename_case(st.session_state["case_id"], new_cid)
                        st.session_state["case_id"] = new_cid
                        st.success(f"Renamed to {new_cid}")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            st.markdown("---")
            st.caption("⚠️ Danger zone")
            confirm = st.checkbox("Tick to enable delete", key="_delete_confirm")
            if st.button("🗑️ Delete this case permanently",
                         key="_delete_btn", disabled=not confirm):
                ds_data.delete_case(st.session_state["case_id"])
                st.session_state["case_id"] = ""
                st.session_state["applicant_name"] = ""
                st.session_state["state"] = _empty_state()
                st.success("Case deleted.")
                st.rerun()

    # --- Settings (DS name source toggle lives here) ---
    sidebar_settings()

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"**Case ID:** `{st.session_state.get('case_id', '—')}`"
    )

    intake = st.session_state["state"].setdefault("intake", {})
    with st.sidebar.form("intake_form"):
        st.markdown("### 📥 Application intake")
        intake["applicant_name"] = st.text_input("Applicant trading name",
            value=intake.get("applicant_name", ""))
        intake["applicant_legal_entity"] = st.text_input("Legal entity",
            value=intake.get("applicant_legal_entity", ""))
        intake["regime_applied_for"] = st.selectbox("Regime applied for", REGIMES,
            index=REGIMES.index(intake["regime_applied_for"])
                  if intake.get("regime_applied_for") in REGIMES else 0)
        intake["crypto_activities"] = st.multiselect("Cryptoasset activities (FCA Q3.1)",
            CRYPTO_ACTIVITIES, default=intake.get("crypto_activities", []))
        intake["case_officer"] = st.text_input("Case officer",
            value=intake.get("case_officer", ""))
        intake["submission_date"] = st.date_input("Submission date",
            value=intake.get("submission_date") or date.today()).isoformat()

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Wallets & territories</div>', unsafe_allow_html=True)
        intake["declared_wallets"] = st.text_area("Declared wallets (comma-separated)",
            value=intake.get("declared_wallets", ""), height=80)
        intake["declared_territories"] = st.text_input("Declared territories of operation",
            value=intake.get("declared_territories", ""))

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Volume & assets</div>', unsafe_allow_html=True)
        intake["declared_volume_usd"] = st.text_input("Declared volume USD (window-period)",
            value=intake.get("declared_volume_usd", ""))
        intake["reconciliation_window_days"] = st.number_input("Reconciliation window (days)",
            min_value=1, max_value=3650,
            value=int(intake.get("reconciliation_window_days") or 90))
        intake["declared_user_count"] = st.text_input("Declared user count",
            value=intake.get("declared_user_count", ""))
        intake["declared_balance_usd"] = st.text_input("Declared balance USD",
            value=intake.get("declared_balance_usd", ""))
        intake["declared_assets"] = st.text_input("Declared supported assets",
            value=intake.get("declared_assets", ""))
        intake["declared_transaction_count"] = st.text_input("Declared transaction count (FCA Q3.2)",
            value=intake.get("declared_transaction_count", ""))

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Business model & controls</div>', unsafe_allow_html=True)
        intake["declared_business_model"] = st.text_area("Declared business model",
            value=intake.get("declared_business_model", ""), height=70)
        intake["declared_custody_arrangement"] = st.selectbox("Custody arrangement",
            CUSTODY_OPTIONS,
            index=CUSTODY_OPTIONS.index(intake.get("declared_custody_arrangement", ""))
                  if intake.get("declared_custody_arrangement") in CUSTODY_OPTIONS else 0)
        intake["flow_of_funds_description"] = st.text_area("Flow of funds description",
            value=intake.get("flow_of_funds_description", ""), height=70)

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Governance</div>', unsafe_allow_html=True)
        intake["declared_ubos"] = st.text_area("Declared UBOs (comma-separated)",
            value=intake.get("declared_ubos", ""), height=60)
        intake["declared_affiliated_firms"] = st.text_area("Declared affiliated firms",
            value=intake.get("declared_affiliated_firms", ""), height=60)
        intake["declared_peer_cohort"] = st.text_area("Declared peer cohort (comma-separated)",
            value=intake.get("declared_peer_cohort", ""), height=60)
        intake["group_structure"] = st.text_area("Group structure / close links",
            value=intake.get("group_structure", ""), height=60)
        intake["mlro_name"] = st.text_input("MLRO name",
            value=intake.get("mlro_name", ""))
        intake["mlro_experience"] = st.text_area("MLRO experience (📝 attestation only)",
            value=intake.get("mlro_experience", ""), height=60)

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Mandatory docs</div>', unsafe_allow_html=True)
        intake["bwra_reference"] = st.text_input("BWRA reference",
            value=intake.get("bwra_reference", ""))
        intake["customer_risk_methodology"] = st.text_area("Customer risk methodology",
            value=intake.get("customer_risk_methodology", ""), height=60)
        intake["blockchain_monitoring_tools"] = st.text_input("Blockchain monitoring tools used",
            value=intake.get("blockchain_monitoring_tools", ""))
        intake["travel_rule_compliance"] = st.text_area("Travel-rule policy summary",
            value=intake.get("travel_rule_compliance", ""), height=60)
        intake["outsourcing_arrangements"] = st.text_area("Outsourcing arrangements",
            value=intake.get("outsourcing_arrangements", ""), height=60)

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Projections (attestation only)</div>', unsafe_allow_html=True)
        intake["financial_projections_y1"] = st.text_input("Year 1 revenue projection (GBP)",
            value=intake.get("financial_projections_y1", ""))
        intake["financial_projections_y3"] = st.text_input("Year 3 revenue projection (GBP)",
            value=intake.get("financial_projections_y3", ""))

        st.markdown('<div style="margin-top:1.2rem; margin-bottom:0.2rem; font-size:0.72rem; font-weight:500; letter-spacing:0.08em; text-transform:uppercase; color:rgba(255,255,255,0.65); border-bottom:1px solid rgba(255,255,255,0.15); padding-bottom:0.25rem;">Prior denials</div>', unsafe_allow_html=True)
        intake["prior_denials_yn"] = st.selectbox("Any prior denials in last 5y?", ["No", "Yes"],
            index=["No", "Yes"].index(intake.get("prior_denials_yn", "No")))
        intake["prior_denial_detail"] = st.text_area("If Yes — jurisdictions + dates",
            value=intake.get("prior_denial_detail", ""), height=60)


        st.divider()
        st.subheader("📋 FCA Application Fields")
        st.caption("Mapped to the FCA Application for Registration as a Cryptoasset Business form")

        st.session_state.setdefault("crypto_activities", "")
        st.session_state.crypto_activities = st.selectbox("Cryptoasset Activities (FCA Q3.1)",
            ["", "Fiat-to-Crypto Exchange", "Crypto-to-Crypto Exchange", "Custodian Wallet Provider", "ATM Operator", "Multiple (see note)"],
            index=["", "Fiat-to-Crypto Exchange", "Crypto-to-Crypto Exchange", "Custodian Wallet Provider", "ATM Operator", "Multiple (see note)"].index(st.session_state.get("crypto_activities", "")) if st.session_state.get("crypto_activities", "") in ["", "Fiat-to-Crypto Exchange", "Crypto-to-Crypto Exchange", "Custodian Wallet Provider", "ATM Operator", "Multiple (see note)"] else 0)
        st.caption("🔗 Validated by: Phase 3 counterparty mix (P3.1)")

        st.session_state.setdefault("declared_transaction_count", "")
        st.session_state.declared_transaction_count = st.text_input("Declared Transaction Count (per period)", value=st.session_state.declared_transaction_count)
        st.caption("🔗 Validated by: Phase 2 P2.2 + Phase 3 P3.4")

        st.session_state.setdefault("mlro_name", "")
        st.session_state.mlro_name = st.text_input("MLRO Name", value=st.session_state.mlro_name)
        st.caption("🔗 Validated by: Companies House officers lookup")

        st.session_state.setdefault("mlro_experience", "")
        st.session_state.mlro_experience = st.text_area("MLRO Experience & Qualifications", value=st.session_state.mlro_experience, height=60)
        st.caption("📝 Attestation only")

        st.session_state.setdefault("financial_projections_y1", "")
        st.session_state.financial_projections_y1 = st.text_input("Year 1 Revenue Projection (GBP)", value=st.session_state.financial_projections_y1)
        st.caption("📝 Attestation only")

        st.session_state.setdefault("financial_projections_y3", "")
        st.session_state.financial_projections_y3 = st.text_input("Year 3 Revenue Projection (GBP)", value=st.session_state.financial_projections_y3)
        st.caption("📝 Attestation only")

        st.session_state.setdefault("flow_of_funds_description", "")
        st.session_state.flow_of_funds_description = st.text_area("Flow of Funds Description", value=st.session_state.flow_of_funds_description, height=60)
        st.caption("🔗 Partially validated by: Phase 3 sankey (P3.2)")

        st.session_state.setdefault("bwra_reference", "")
        st.session_state.bwra_reference = st.text_input("Business-Wide Risk Assessment (BWRA) Reference", value=st.session_state.bwra_reference)
        st.caption("🔗 Partially validated by: Phase 5 P5.1/P5.6")

        st.session_state.setdefault("customer_risk_methodology", "")
        st.session_state.customer_risk_methodology = st.text_area("Customer Risk Assessment Methodology", value=st.session_state.customer_risk_methodology, height=60)
        st.caption("🔗 Partially validated by: Phase 4 P4.2/P4.3")

        st.session_state.setdefault("blockchain_monitoring_tools", "")
        st.session_state.blockchain_monitoring_tools = st.text_input("Blockchain Monitoring Tools Used", value=st.session_state.blockchain_monitoring_tools, placeholder="e.g. Chainalysis, Elliptic, TRM Labs")
        st.caption("📝 Attestation only")

        st.session_state.setdefault("group_structure", "")
        st.session_state.group_structure = st.text_area("Group Structure / Close Links", value=st.session_state.group_structure, height=60)
        st.caption("🔗 Validated by: Affiliated Firms + Companies House PSC")

        st.session_state.setdefault("travel_rule_compliance", "")
        st.session_state.travel_rule_compliance = st.text_area("Travel Rule Compliance (Part 7A MLR)", value=st.session_state.travel_rule_compliance, height=60)
        st.caption("📝 Attestation only")

        st.session_state.setdefault("outsourcing_arrangements", "")
        st.session_state.outsourcing_arrangements = st.text_area("Outsourcing Arrangements", value=st.session_state.outsourcing_arrangements, height=60)
        st.caption("📝 Attestation only")

        saved = st.form_submit_button("💾 Save intake")
        if saved:
            st.session_state["applicant_name"] = (
                intake.get("applicant_name", "")
                or st.session_state.get("applicant_name", "")
            )
            commit()
            st.success("Intake saved.")


# ---------------------------------------------------------------------------
# Helpers — applicant resolution (#1: prefer legal entity for DS queries)
# ---------------------------------------------------------------------------

# DS-query name resolution.
#
# Important asymmetry between Chainalysis Data Solutions and Companies House:
#   - DS attributes on-chain activity to the *trading name* (e.g. 'Coinbase.com').
#     The legal entity name ('CB Payments') typically returns ZERO rows in DS
#     because Chainalysis labels clusters by brand, not by registered company.
#   - Companies House is the opposite — it registers under the legal entity.
#
# So we default DS lookups to the trading name, and CH lookups to the legal
# entity (handled separately in the CH section of Phase 0). Per-case override
# lives in session_state["ds_name_source"]: "trading" | "legal".

def _ds_query_name_source() -> str:
    """Which intake field this case uses for DS queries. Defaults to trading name."""
    return st.session_state.get("ds_name_source", "trading")


def _ds_query_name() -> str | None:
    """Returns the name to use for DS queries (trading or legal, per toggle).
    Falls back to the other field if the chosen one is blank, with a caption.
    Warns + returns None if both empty.
    """
    intake = st.session_state["state"].get("intake", {})
    trading = (intake.get("applicant_name") or "").strip()
    legal = (intake.get("applicant_legal_entity") or "").strip()
    source = _ds_query_name_source()
    primary = trading if source == "trading" else legal
    fallback = legal if source == "trading" else trading
    if primary:
        return primary
    if fallback:
        return fallback
    st.warning("Enter an applicant trading name or legal entity in the sidebar intake form first.")
    return None


def _ds_name_banner(scope: str = "tab") -> None:
    """Compact grey caption on every phase tab showing which intake field is
    being sent to DS. The toggle to swap fields lives in the sidebar
    ⚙️ Settings expander so it isn't repeated on every tab.

    ``scope`` is no longer needed (kept for back-compat with callers).
    """
    intake = st.session_state["state"].get("intake", {})
    trading = (intake.get("applicant_name") or "").strip()
    legal = (intake.get("applicant_legal_entity") or "").strip()
    if not (trading or legal):
        return
    source = _ds_query_name_source()
    chosen = trading if source == "trading" else legal
    src_label = "Trading name" if source == "trading" else "Legal entity"
    fallback_note = ""
    if not chosen:
        chosen = legal if source == "trading" else trading
        fallback_note = f" (falling back from empty {src_label})"
        src_label = "Legal entity" if source == "trading" else "Trading name"
    st.caption(
        f"DS queries → **{src_label}** `{chosen}`{fallback_note} "
        f"· _change in sidebar → ⚙️ Settings_"
    )


def sidebar_settings() -> None:
    """⚙️ Settings expander in the sidebar — currently just the DS-name toggle.
    Designed to be the single home for case-officer preferences."""
    intake = st.session_state["state"].get("intake", {})
    trading = (intake.get("applicant_name") or "").strip()
    legal = (intake.get("applicant_legal_entity") or "").strip()
    with st.sidebar.expander("⚙️ Settings", expanded=False):
        st.markdown("**Data Solutions name source**")
        st.caption(
            "Which intake field to send to Chainalysis. Chainalysis attributes "
            "by brand (e.g. `Coinbase.com`), not by registered company "
            "(e.g. `CB Payments`), so **Trading name** is the default — only "
            "switch if your applicant is labelled by its legal entity in DS."
        )
        options = {"trading": f"Trading name  ·  `{trading or '— empty —'}`",
                   "legal":   f"Legal entity  ·  `{legal or '— empty —'}`"}
        current = _ds_query_name_source()
        picked = st.radio(
            "Use for DS queries:",
            options=list(options.keys()),
            format_func=lambda k: options[k],
            index=list(options.keys()).index(current),
            key="_ds_source_radio",
        )
        if picked != current:
            st.session_state["ds_name_source"] = picked
            st.rerun()


def _wallets_list() -> list[str]:
    raw = st.session_state["state"].get("intake", {}).get("declared_wallets", "")
    return [w.strip() for w in (raw or "").split(",") if w.strip()]


def _peers_list() -> list[str]:
    raw = st.session_state["state"].get("intake", {}).get("declared_peer_cohort", "")
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _clear_phase_button(phase: str) -> None:
    """Render a small 'clear results' button at the top of each phase tab (#4)."""
    cols = st.columns([5, 1])
    with cols[1]:
        if st.button("🗑️ Clear results", key=f"clear_{phase}",
                     help=f"Wipe saved query results for {phase} (intake + decision are kept)."):
            clear_phase_results(phase)
            ds_data.log_audit(st.session_state["case_id"], "clear_results", phase)
            st.rerun()


# ---------------------------------------------------------------------------
# Tab: Case Summary
# ---------------------------------------------------------------------------

def tab_case_summary() -> None:
    st.header("Case Summary")
    intake = st.session_state["state"].get("intake", {})
    p0 = st.session_state["state"].get("phase0", {})
    p1 = st.session_state["state"].get("phase1", {})
    p5 = st.session_state["state"].get("phase5", {})
    p8 = st.session_state["state"].get("phase8", {})

    cols = st.columns(3)
    cols[0].markdown(f"**Applicant**\n\n{intake.get('applicant_name','—')}")
    cols[1].markdown(f"**Legal entity**\n\n{intake.get('applicant_legal_entity','—')}")
    cols[2].markdown(f"**Regime**\n\n{intake.get('regime_applied_for','—')}")

    st.markdown("---")

    st.subheader("🛑 Hard-stop indicators")
    indicators = []
    if (p0.get("perimeter_status") or "").startswith("🛑"):
        indicators.append("Perimeter hit (Phase 0)")
    if p0.get("sanctions_severe_hits", 0):
        indicators.append(f"{p0['sanctions_severe_hits']} SEVERE sanctions hits")
    if p0.get("fca_warning_match"):
        indicators.append(f"FCA warning list match: {', '.join(p0['fca_warning_match'])}")
    if p5.get("severe_categories"):
        indicators.append(f"Severe illicit categories: {', '.join(p5['severe_categories'])}")
    if p1.get("mlro_match_status") == "missing":
        indicators.append("MLRO not found among CH officers")
    if not indicators:
        st.success("No hard-stops recorded yet.")
    else:
        for i in indicators:
            st.error(i)

    st.subheader("📥 Outstanding intake inputs")
    expected = [
        "applicant_name", "declared_wallets", "declared_volume_usd",
        "declared_user_count", "declared_business_model",
        "declared_custody_arrangement", "declared_ubos", "declared_peer_cohort",
        "mlro_name", "bwra_reference", "crypto_activities",
        "declared_transaction_count", "mlro_experience",
        "blockchain_monitoring_tools", "group_structure",
    ]
    missing = [k for k in expected if not intake.get(k)]
    if missing:
        st.warning("Missing: " + ", ".join(missing))
    else:
        st.success("All key intake fields recorded.")

    st.subheader("📊 Phase result snapshot")
    for phase_key, label in [
        ("phase0", "Phase 0 — Triage"),
        ("phase1", "Phase 1 — Identity"),
        ("phase2", "Phase 2 — Verify"),
        ("phase3", "Phase 3 — Behaviour"),
        ("phase5", "Phase 5 — Risk"),
        ("phase7", "Phase 7 — Peers"),
    ]:
        results = st.session_state["state"].get(phase_key, {}).get("_results", {})
        if results:
            tiles = ", ".join(f"`{k}`" for k in results.keys())
            st.markdown(f"- **{label}** — {len(results)} run(s): {tiles}")
        else:
            st.markdown(f"- {label} — _no runs yet_")

    st.subheader("🧾 Decision so far")
    outcome = p8.get("outcome", "Pending")
    outcome_class = (
        "outcome-pending" if outcome == "Pending"
        else "outcome-approve" if outcome.startswith("Approve")
        else "outcome-refuse" if outcome.startswith(("Refuse", "Minded"))
        else "outcome-other"
    )
    note = p8.get("analyst_note") or "—"
    reviewer = p8.get("second_reviewer") or "—"
    st.markdown(
        f"""<div class="decision-card">
          <h3>Outcome: <span class="{outcome_class}">{_h(outcome)}</span></h3>
          <p><strong>Analyst note:</strong> {_h(note)}</p>
          <p><strong>Second reviewer:</strong> {_h(reviewer)}</p>
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab: Phase 0 — Triage
# ---------------------------------------------------------------------------

def tab_phase0() -> None:
    st.header("Phase 0 — Triage")
    _clear_phase_button("phase0")
    name = _ds_query_name()
    if not name:
        return
    _ds_name_banner(scope="p0")

    p0 = st.session_state["state"].setdefault("phase0", {})

    st.subheader("🛑 C4 — Perimeter pre-check")
    if st.button("Run perimeter check", key="run_c4"):
        df = run_query(Q.sql_perimeter_check(name, ds_data.FCA_REGISTERED), "Perimeter check", 5)
        save_result("phase0", "perimeter", df, label="Perimeter check")
        if not df.empty:
            row = df.iloc[0].to_dict()
            p0["perimeter_status"] = row.get("Perimeter Status")
            p0["register_status"] = row.get("Register Status")
            commit()
    render_saved("phase0", "perimeter",
                 explain_empty="Check the entity name spelling — DS may store it differently (e.g. 'Coinbase.com' not 'Coinbase').")

    st.subheader("🛑 C5 — Sanctions / severity screen")
    wallets = _wallets_list()
    if not wallets:
        st.info("No declared wallets in intake — add comma-separated addresses.")
    else:
        if st.button("Run sanctions screen", key="run_c5"):
            df = run_query(Q.sql_sanctions_screen(wallets), "Sanctions screen", 5)
            save_result("phase0", "sanctions", df, label="Sanctions screen")
            if not df.empty and "Severity" in df.columns:
                p0["sanctions_severe_hits"] = int((df["Severity"] == "severe").sum())
                commit()
        render_saved("phase0", "sanctions")

    st.subheader("⚠️ C5b — FCA unauthorised warning list")
    warn = ds_data.check_fca_warnings(name)
    if warn["warning_hit"]:
        st.error(f"Match against FCA warning list: {', '.join(warn['matches'])}")
        p0["fca_warning_match"] = warn["matches"]
    else:
        st.success(f"No match against FCA warning list ({warn['warning_list_size']} entries checked).")
        p0["fca_warning_match"] = []
    commit()

    # --- Companies House (search → pick → fetch)
    st.subheader("🏛️ Companies House PSC + officers lookup")
    intake = st.session_state["state"]["intake"]
    legal_entity = intake.get("applicant_legal_entity", "") or ""
    trading_name = intake.get("applicant_name", "") or ""
    search_source = "Legal entity" if legal_entity.strip() else "Trading name"
    search_input_raw = legal_entity.strip() or trading_name
    cleaned = ds_data.clean_company_name(search_input_raw)
    st.caption(
        f"Will search Companies House for **`{cleaned}`** "
        f"(using *{search_source}* from intake)."
    )
    include_dissolved = st.checkbox(
        "Include dissolved companies in search",
        value=False, key="ch_include_dissolved",
    )
    if st.button("🔍 Search Companies House", key="run_ch_search"):
        search = ds_data.companies_house_search_candidates(
            legal_entity=legal_entity, trading_name=trading_name,
            include_dissolved=include_dissolved,
        )
        p0["ch_search"] = search
        p0.pop("companies_house", None)
        commit()
        ds_data.log_audit(
            st.session_state["case_id"], "ch_search",
            f"queried '{search.get('queried_name')}' "
            f"(source={search.get('source_field')}, include_dissolved={include_dissolved}) "
            f"-> {len(search.get('candidates') or [])} candidates",
        )

    search = p0.get("ch_search")
    if search:
        if search.get("error"):
            st.warning(search["error"])
        candidates = search.get("candidates") or []
        if candidates:
            st.write(f"**{len(candidates)} candidate(s)** for `{search.get('queried_name')}`:")
            labels = [
                f"{c.get('company_number','?')} — {c.get('title','?')} "
                f"({c.get('company_status','?')}, {c.get('date_of_creation','?')})"
                for c in candidates
            ]
            picked_label = st.radio("Pick the legal entity to fetch:",
                                     labels, index=0, key="ch_candidate_picker")
            picked_idx = labels.index(picked_label)
            picked = candidates[picked_idx]
            st.caption(f"📍 {picked.get('address_snippet') or '— no address —'}")
            if st.button("⬇️ Fetch PSC + officers for selected company", key="run_ch_fetch"):
                full = ds_data.companies_house_fetch_company(picked["company_number"])
                # (#E) — redact PII before persisting to SQLite (DOB + home address
                # for PSCs/officers). The audit-trail still captures who was picked.
                full = ds_data.redact_ch_pii(full)
                # (#5) — record selection trail in payload
                p0["companies_house"] = {
                    "queried_name": search.get("queried_name"),
                    "search_source_field": search.get("source_field"),
                    "candidates_returned": len(candidates),
                    "candidate_titles": [c.get("title") for c in candidates],
                    "selected_company": picked,
                    "selected_index": picked_idx,
                    **full,
                }
                commit()
                ds_data.log_audit(
                    st.session_state["case_id"], "ch_fetch",
                    f"selected #{picked_idx+1} of {len(candidates)}: "
                    f"{picked.get('company_number')} ({picked.get('title')})",
                )
                # (#2) — automatic MLRO cross-check
                _run_mlro_check(p0["companies_house"])

    fetched = p0.get("companies_house")
    if fetched:
        _render_ch_record(fetched)

    st.subheader("🎚️ C8 — Triage risk tier")
    if st.button("Calculate risk tier", key="run_c8"):
        df = run_query(Q.sql_risk_tier(name, ds_data.FCA_REGISTERED), "Risk tier", 5)
        save_result("phase0", "risk_tier", df, label="Risk tier")
        if not df.empty:
            p0["risk_tier"] = df.iloc[0].get("Risk Tier")
            commit()
    render_saved("phase0", "risk_tier")

    # --- C7 affiliate reconciliation (Tier 2 #7)
    st.subheader("🔗 C7 — Affiliated firm bilateral flow reconciliation")
    affiliates_raw = intake.get("declared_affiliated_firms", "") or ""
    affiliates = [a.strip() for a in affiliates_raw.split(",") if a.strip()]
    if not affiliates:
        st.caption("_Add comma-separated firm names to **Declared affiliated firms** in intake to enable this check._")
    else:
        st.caption(f"Checking bilateral on-chain flow with {len(affiliates)} declared affiliate(s): {', '.join(affiliates)}")
        if st.button("Run affiliate reconciliation", key="run_c7"):
            df = run_query(Q.sql_affiliate_reconciliation(name, affiliates),
                           "Affiliate reconciliation", est_seconds=120, async_=True, max_wait=600)
            save_result("phase0", "affiliates", df, label="Affiliate reconciliation")
        render_saved("phase0", "affiliates",
                     explain_empty="No bilateral flow observed with any declared affiliate in 90d.")


    st.subheader("📜 C6 — Prior denial attestation")
    st.write(f"**Declared Y/N:** {intake.get('prior_denials_yn', '—')}")
    st.write(f"**Detail:** {intake.get('prior_denial_detail') or '—'}")


# ---------------------------------------------------------------------------
# MLRO cross-check (#2)
# ---------------------------------------------------------------------------

def _render_ch_record(ch: dict) -> None:
    """Render the fetched Companies House payload as case-officer-friendly
    summary + tables (with CSV downloads), instead of a raw JSON dump."""
    company = ch.get("selected_company") or {}
    officers = ch.get("officers") or []
    pscs = ch.get("psc") or []

    # --- Summary block ---
    st.success(
        f"Loaded **{company.get('title','?')}** "
        f"(company number `{company.get('company_number','?')}`)"
    )
    meta_cols = st.columns(4)
    meta_cols[0].markdown(f"**Status**\n\n{company.get('company_status','—')}")
    meta_cols[1].markdown(f"**Incorporated**\n\n{company.get('date_of_creation','—')}")
    meta_cols[2].markdown(f"**Officers**\n\n{len(officers)}")
    meta_cols[3].markdown(f"**PSCs**\n\n{len(pscs)}")
    if company.get("address_snippet"):
        st.markdown(f"📍 **Registered address:** {company['address_snippet']}")
    st.caption(
        f"Picked candidate #{(ch.get('selected_index') or 0)+1} of "
        f"{ch.get('candidates_returned','?')} returned from search for "
        f"`{ch.get('queried_name','?')}` "
        f"(via *{ch.get('search_source_field','?').replace('_',' ')}*)."
    )

    # --- Officers table ---
    st.markdown("#### 👥 Officers")
    show_resigned = st.checkbox(
        "Include resigned officers", value=False, key="_ch_show_resigned",
        help="By default, only currently-appointed officers are shown.",
    )
    officer_rows = []
    for o in officers:
        is_resigned = bool(o.get("resigned_on"))
        if is_resigned and not show_resigned:
            continue
        officer_rows.append({
            "Name": o.get("name", "—"),
            "Role": (o.get("officer_role") or "—").replace("-", " ").title(),
            "Appointed": o.get("appointed_on", "—"),
            "Resigned": o.get("resigned_on") or "",
            "Nationality": o.get("nationality", "—"),
            "Country of Residence": o.get("country_of_residence", "—"),
            "Status": "🔴 Resigned" if is_resigned else "✅ Current",
        })
    if officer_rows:
        odf = pd.DataFrame(officer_rows)
        styled_dataframe(odf, status_cols=["Status"])
        st.download_button(
            "⬇️ Officers as CSV",
            data=odf.to_csv(index=False).encode("utf-8"),
            file_name=f"{st.session_state['case_id']}_ch_officers.csv",
            mime="text/csv",
            key="csv_ch_officers",
        )
    else:
        st.caption("_No officers to display (or all are resigned — tick the box above to include)._")

    # --- PSC table ---
    st.markdown("#### 🧑‍⚖️ Persons with significant control (PSCs)")
    if not pscs:
        st.caption("_No PSCs returned for this company._")
    else:
        psc_rows = []
        for p in pscs:
            nature = p.get("natures_of_control") or []
            psc_rows.append({
                "Name": p.get("name", "—"),
                "Kind": (p.get("kind") or "—").replace("-", " ").title(),
                "Nationality": p.get("nationality", "—"),
                "Country of Residence": p.get("country_of_residence", "—"),
                "Nature of Control": "; ".join(
                    n.replace("-", " ") for n in nature) if nature else "—",
                "Notified": p.get("notified_on", "—"),
                "Status": "🔴 Ceased" if p.get("ceased") else "✅ Current",
            })
        pdf = pd.DataFrame(psc_rows)
        styled_dataframe(pdf, status_cols=["Status"])
        st.download_button(
            "⬇️ PSCs as CSV",
            data=pdf.to_csv(index=False).encode("utf-8"),
            file_name=f"{st.session_state['case_id']}_ch_pscs.csv",
            mime="text/csv",
            key="csv_ch_pscs",
        )

    # --- Raw JSON tucked away ---
    with st.expander("🔧 Raw Companies House payload (for debugging)", expanded=False):
        st.caption("Personal data (DOB, home address) is `[redacted]` before persistence — see redact_ch_pii in utils/data.py.")
        st.json(ch)


def _normalise_name(s: str) -> str:
    """Lowercase, strip punctuation/titles, collapse whitespace."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|sir)\.?\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _run_mlro_check(ch_payload: dict) -> None:
    """Compare intake mlro_name to fetched CH officers list. Stores verdict on phase1."""
    p1 = st.session_state["state"].setdefault("phase1", {})
    intake = st.session_state["state"].get("intake", {})
    mlro = (intake.get("mlro_name") or "").strip()
    if not mlro or mlro.lower().startswith("(") or mlro.lower() == "tbc":
        p1["mlro_match_status"] = "no_mlro_declared"
        commit()
        return
    officers = ch_payload.get("officers") or []
    needle = _normalise_name(mlro)
    needle_tokens = set(needle.split())
    matches = []
    for o in officers:
        on = _normalise_name(o.get("name") or "")
        if not on:
            continue
        if needle in on or on in needle:
            matches.append(o)
            continue
        # Token overlap fallback (handles "Doe, John" vs "John Doe")
        tokens = set(on.split())
        if needle_tokens and len(needle_tokens & tokens) >= max(2, len(needle_tokens) - 1):
            matches.append(o)
    p1["mlro_match_status"] = "matched" if matches else "missing"
    p1["mlro_matches"] = [
        {"name": m.get("name"), "role": m.get("officer_role"),
         "appointed_on": m.get("appointed_on")}
        for m in matches
    ]
    p1["mlro_checked_against"] = len(officers)
    commit()
    ds_data.log_audit(
        st.session_state["case_id"], "mlro_check",
        f"mlro='{mlro}' vs {len(officers)} officers -> {p1['mlro_match_status']}",
    )


# ---------------------------------------------------------------------------
# Tab: Phase 1 — Identity
# ---------------------------------------------------------------------------

def tab_phase1() -> None:
    st.header("Phase 1 — Identity")
    _clear_phase_button("phase1")
    name = _ds_query_name()
    if not name:
        return
    _ds_name_banner(scope="p1")
    intake = st.session_state["state"].get("intake", {})
    p1 = st.session_state["state"].setdefault("phase1", {})

    # --- P1.1 Wallet attribution (#13)
    st.subheader("🔗 P1.1 — Declared wallet attribution")
    wallets = _wallets_list()
    if not wallets:
        st.info("No declared wallets in intake — add comma-separated addresses to enable this check.")
    else:
        st.caption(f"Looking up {len(wallets)} declared wallet(s) across all chains in `cross_chain.clusters`.")
        if st.button("Run wallet attribution", key="run_p11"):
            df = run_query(Q.sql_wallet_attribution(wallets), "Wallet attribution", 5)
            save_result("phase1", "wallet_attribution", df, label="Wallet attribution")
        render_saved("phase1", "wallet_attribution",
                     explain_empty="Wallet addresses may be unattributed in the Chainalysis dataset (no cluster match across any chain).")

    # --- P1.2 Time on chain
    st.subheader("🕰️ P1.2 — Time on chain")
    if st.button("Run time-on-chain", key="run_p12"):
        df = run_query(Q.sql_time_on_chain(name), "Time on chain", 5)
        save_result("phase1", "time_on_chain", df, label="Time on chain")
        if not df.empty:
            p1["time_on_chain"] = df.iloc[0].to_dict()
            commit()
    render_saved("phase1", "time_on_chain",
                 explain_empty="No cluster_summary rows match this entity. Try the legal-entity field if you used the trading name (or vice-versa).")

    # --- P1.3 Cluster lineage (Tier 2 #6)
    st.subheader("📜 P1.3 — Cluster lineage (category-change events)")
    if st.button("Run cluster lineage", key="run_p13"):
        df = run_query(Q.sql_cluster_lineage(name), "Cluster lineage", 10)
        save_result("phase1", "cluster_lineage", df, label="Cluster lineage")
    render_saved("phase1", "cluster_lineage",
                 explain_empty="No category-change events recorded — note: Chainalysis populates this dataset mainly for sanctioned-entity reclassifications, absence is not proof of stability.")

    # --- P1.4 Declared territories vs observed customer geo (Top 4 #3)
    st.subheader("🌍 P1.4 — Declared territories vs observed customer geo (WGS)")
    declared_terr = (intake.get("declared_territories", "") or "").strip()
    if not declared_terr:
        st.caption("_Add ISO country codes (e.g. `GB,IE,DE`) to **Declared territories** in intake to enable comparison._")
    else:
        st.caption(f"Comparing declared territories ({declared_terr}) to observed inflow-counterparty geo in last 30 days.")
    if st.button("Run geo comparison", key="run_p14"):
        df = run_query(Q.sql_declared_vs_observed_geo(name, declared_terr),
                       "Declared vs observed geo", est_seconds=120,
                       async_=True, max_wait=600)
        save_result("phase1", "geo_comparison", df, label="Declared vs observed geo")
    render_saved("phase1", "geo_comparison",
                 explain_empty="No wallet-geo signals matched — WGS coverage is sparser on Solana / newer chains. Or, no inflows from clusters with country attribution in 30d.")


    # --- P1.5 OSINT
    st.subheader("📰 P1.5 — OSINT / adverse-media scan")
    cols = st.columns(2)
    if cols[0].button("Run OSINT scan (summary)", key="run_p15"):
        df = run_query(Q.sql_osint(name, _wallets_list()), "OSINT scan", est_seconds=120, async_=True, max_wait=600)
        save_result("phase1", "osint_summary", df, label="OSINT summary")
        if not df.empty and "OSINT Source" in df.columns:
            p1["osint_sources"] = df["OSINT Source"].tolist()
            commit()
    osint_limit = cols[1].slider("Findings to fetch", min_value=25, max_value=500,
                                  value=100, step=25, key="osint_limit")
    if st.button("Fetch individual findings", key="run_p15_details"):
        df = run_query(Q.sql_osint_details(name, _wallets_list(), limit=osint_limit),
                       f"OSINT details (top {osint_limit})", est_seconds=120, async_=True, max_wait=600)
        save_result("phase1", "osint_details", df, label=f"OSINT individual findings (top {osint_limit})")
    st.markdown("**Summary by source**")
    render_saved("phase1", "osint_summary",
                 explain_empty="No OSINT hits in third_party_osint for this applicant's clusters or declared wallets.")
    st.markdown("**Individual findings**")
    render_saved("phase1", "osint_details",
                 empty_msg="Click 'Fetch individual findings' to see address-level OSINT rows.")

    # --- MLRO cross-check (#2)
    st.subheader("🔎 P1.6 — MLRO cross-check (against Companies House officers)")
    intake = st.session_state["state"]["intake"]
    mlro = (intake.get("mlro_name") or "").strip()
    status = p1.get("mlro_match_status")
    p0 = st.session_state["state"].get("phase0", {})
    ch = p0.get("companies_house")
    if not mlro:
        st.info("No MLRO declared in intake.")
    elif not ch:
        st.warning("Fetch Companies House officers in Phase 0 first, then this check runs automatically.")
    elif status == "no_mlro_declared":
        st.info("No MLRO name on file — placeholder text (TBC / awaiting) treated as undeclared.")
    elif status == "matched":
        matches = p1.get("mlro_matches", [])
        st.success(f"✅ MLRO `{mlro}` matches {len(matches)} officer record(s) (checked against {p1.get('mlro_checked_against', 0)} officers).")
        for m in matches:
            st.write(f"- **{m['name']}** — {m['role']} (appointed {m['appointed_on']})")
    elif status == "missing":
        st.error(f"🛑 MLRO `{mlro}` was NOT found among {p1.get('mlro_checked_against', 0)} Companies House officers. Hard-stop indicator raised — propagated to Case Summary.")
    else:
        st.caption("Cross-check will run automatically the next time you fetch CH officers.")
    if ch and st.button("Re-run MLRO check", key="rerun_mlro"):
        _run_mlro_check(ch)
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Phase 2 — Verify
# ---------------------------------------------------------------------------

def tab_phase2() -> None:
    st.header("Phase 2 — Verify")
    _clear_phase_button("phase2")
    name = _ds_query_name()
    if not name:
        return
    _ds_name_banner(scope="p2")
    p2 = st.session_state["state"].setdefault("phase2", {})
    intake = st.session_state["state"]["intake"]
    window = int(intake.get("reconciliation_window_days") or 90)
    declared = intake.get("declared_volume_usd") or None

    st.subheader(f"🧮 P2.1 — Volume reconciliation ({window}-day window)")
    if st.button("Run volume reconciliation", key="run_p21"):
        df = run_query(Q.sql_volume_reconciliation(name, window, declared),
                       "Volume reconciliation", est_seconds=120, async_=True, max_wait=600)
        save_result("phase2", "volume", df, label="Volume reconciliation")
        if not df.empty:
            p2["volume_reconciliation"] = df.iloc[0].to_dict()
            commit()
    df = render_saved("phase2", "volume")
    if df is not None and not df.empty:
        row = df.iloc[0].to_dict()
        cols = st.columns(3)
        cols[0].metric("Declared", fmt_usd(row.get("Declared (USD)")))
        cols[1].metric("Observed", fmt_usd(row.get("Observed Total (USD)")))
        delta_v = row.get("Delta (USD)")
        cols[2].metric("Delta", fmt_usd(delta_v) if delta_v is not None else "—",
                       delta=f"{row.get('Delta %')}%" if row.get("Delta %") is not None else None)

    # --- P2.2 Time-series chart (#14)
    st.subheader("📈 P2.2 — Volume time series (last 365 days)")
    if st.button("Run volume time series", key="run_p22"):
        df = run_query(Q.sql_volume_timeseries(name, window_days=365),
                       "Volume time series", est_seconds=120, async_=True, max_wait=600)
        save_result("phase2", "timeseries", df, label="Volume time series")
    df = render_saved("phase2", "timeseries",
                      explain_empty="No daily exposure rows in the last 365 days.")
    if df is not None and not df.empty and "Date" in df.columns:
        plot_df = df.melt(id_vars=["Date"], value_vars=["Inflow USD", "Outflow USD"],
                          var_name="Flow", value_name="USD")
        fig = px.area(plot_df, x="Date", y="USD", color="Flow",
                      title=f"Daily flow — {name}", color_discrete_map={
                          "Inflow USD": FCA_DIVERGING["approve"],
                          "Outflow USD": FCA_DIVERGING["refuse"]})
        fig.update_layout(font_family="Source Sans Pro", title_font_color=FCA_PURPLE,
                          plot_bgcolor="#fafafa", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    # --- Cross-chain breakdown (#18)
    st.subheader("⛓️ P2.3 — Cross-chain breakdown")
    if st.button("Run cross-chain breakdown", key="run_p23"):
        df = run_query(Q.sql_cross_chain_breakdown(name, window_days=window),
                       "Cross-chain breakdown", est_seconds=120, async_=True, max_wait=600)
        save_result("phase2", "cross_chain", df, label="Cross-chain breakdown")
    df = render_saved("phase2", "cross_chain")
    if df is not None and not df.empty and "Chain" in df.columns:
        usd_col = [c for c in df.columns if "USD" in c][0]
        fig = px.bar(df, x="Chain", y=usd_col,
                     title=f"Per-chain volume — {name} ({window}d window)",
                     color_discrete_sequence=[FCA_PURPLE])
        fig.update_layout(font_family="Source Sans Pro", title_font_color=FCA_PURPLE,
                          plot_bgcolor="#fafafa", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # --- P2.5 Internal consistency (Tier 2 #8)
    st.subheader("🎯 P2.5 — Internal consistency: declared business model vs tx-size distribution")
    bm = (intake.get("declared_business_model", "") or "").strip()
    if not bm:
        st.caption("_Set **Declared business model** in intake to enable this consistency check._")
    else:
        st.caption(f"Comparing declared model (*{bm}*) to actual tx-size distribution observed in 30 days.")
    if st.button("Run consistency check", key="run_p25"):
        df = run_query(Q.sql_internal_consistency(name, bm),
                       "Internal consistency", est_seconds=120,
                       async_=True, max_wait=600)
        save_result("phase2", "consistency", df, label="Internal consistency")
    render_saved("phase2", "consistency",
                 explain_empty="No transfers observed in 30-day window.")


# ---------------------------------------------------------------------------
# Tab: Phase 3 — Behaviour
# ---------------------------------------------------------------------------

def tab_phase3() -> None:
    st.header("Phase 3 — Behaviour")
    _clear_phase_button("phase3")
    name = _ds_query_name()
    if not name:
        return
    _ds_name_banner(scope="p3")
    p3 = st.session_state["state"].setdefault("phase3", {})

    st.subheader("🥧 P3.1 — Counterparty category mix (90d)")
    if st.button("Run counterparty mix", key="run_p31"):
        df = run_query(Q.sql_counterparty_mix(name), "Counterparty mix", est_seconds=120, async_=True, max_wait=600)
        save_result("phase3", "counterparty_mix", df, label="Counterparty mix")
        if not df.empty and "Category" in df.columns:
            p3["counterparty_categories"] = df["Category"].tolist()
            commit()
    df = render_saved("phase3", "counterparty_mix",
                      explain_empty="No counterparty exposure rows in the 90-day window.")
    if df is not None and not df.empty and "USD (in + out, 90d)" in df.columns:
        fig = px.pie(df, names="Category", values="USD (in + out, 90d)",
                     title="Counterparty category mix, USD (in + out, 90d)",
                     color_discrete_sequence=FCA_PALETTE)
        fig.update_layout(font_family="Source Sans Pro", title_font_color=FCA_PURPLE)
        st.plotly_chart(fig, use_container_width=True)

    # --- P3.2 Sankey (#15)
    st.subheader("🌊 P3.2 — Counterparty flow Sankey (90d, top 15 by USD)")
    if st.button("Run flow Sankey", key="run_p32"):
        df = run_query(Q.sql_counterparty_flows_sankey(name, top_n=15),
                       "Counterparty flow Sankey", est_seconds=120, async_=True, max_wait=600)
        save_result("phase3", "sankey", df, label="Counterparty flow Sankey")
    df = render_saved("phase3", "sankey", csv_button=True,
                      explain_empty="No category flows in window.")
    if df is not None and not df.empty and {"Source", "Target", "USD"}.issubset(df.columns):
        nodes = pd.unique(pd.concat([df["Source"], df["Target"]])).tolist()
        node_idx = {n: i for i, n in enumerate(nodes)}
        fig = go.Figure(go.Sankey(
            node=dict(label=nodes, pad=15, thickness=20,
                      color=[FCA_PURPLE if n == name else "#d8b4c4" for n in nodes]),
            link=dict(
                source=[node_idx[s] for s in df["Source"]],
                target=[node_idx[t] for t in df["Target"]],
                value=df["USD"].tolist(),
            ),
        ))
        fig.update_layout(title_text=f"Flow Sankey — {name} (90d)", font_size=11)
        st.plotly_chart(fig, use_container_width=True)

    # --- P3.3 Top 25 named counterparties (Top 4 #1)
    st.subheader("🏛️ P3.3 — Top 25 named counterparties (90d, with risk flag)")
    st.caption("Names the specific firms / entities Coinbase transacts with, not just category buckets. Use this for refusal-notice citations.")
    if st.button("Run top counterparties", key="run_p33"):
        df = run_query(Q.sql_top_counterparties(name, limit=25),
                       "Top counterparties", est_seconds=120, async_=True, max_wait=600)
        save_result("phase3", "top_counterparties", df, label="Top counterparties")
    render_saved("phase3", "top_counterparties",
                 explain_empty="No named counterparties in 90d — applicant may transact mostly with unhosted wallets (see Phase 4 P4.3).")
    render_counterparty_crosslinks("phase3", "top_counterparties")


# ---------------------------------------------------------------------------
# Tab: Phase 4 — Controls (display only)
# ---------------------------------------------------------------------------

def tab_phase4() -> None:
    st.header("Phase 4 — Controls")
    _clear_phase_button("phase4")
    _ds_name_banner(scope="p4")
    intake = st.session_state["state"]["intake"]
    p4 = st.session_state["state"].setdefault("phase4", {})
    st.subheader("🔐 Custody attestation (declared)")

    # ↓ (declared attestation block follows below)
    for k, lbl in [
        ("declared_custody_arrangement", "Custody arrangement"),
        ("declared_business_model", "Business model"),
        ("customer_risk_methodology", "Customer risk methodology"),
        ("travel_rule_compliance", "Travel-rule compliance"),
        ("blockchain_monitoring_tools", "Blockchain monitoring tools"),
        ("outsourcing_arrangements", "Outsourcing arrangements"),
    ]:
        st.write(f"**{lbl}:** {intake.get(k) or '—'}")

    # --- P4.3 Self-hosted wallet interaction profile (Top 4 #4)
    st.subheader("🏘️ P4.3 — Self-hosted wallet interaction profile")
    name_for_query = _ds_query_name()
    if name_for_query:
        st.caption("Splits inflow/outflow USD by whether the counterparty was a named entity vs an unhosted wallet. Heavy unhosted = direct-retail / self-custody-friendly. Heavy named = institutional / B2B.")
        if st.button("Run self-hosted profile", key="run_p43"):
            df = run_query(Q.sql_self_hosted_profile(name_for_query),
                           "Self-hosted profile", est_seconds=120, async_=True, max_wait=600)
            save_result("phase4", "self_hosted", df, label="Self-hosted profile")
        render_saved("phase4", "self_hosted",
                     explain_empty="No exposure rows in 90d.")

    new_attested = bool(
        intake.get("declared_custody_arrangement") and intake.get("declared_business_model"))
    if p4.get("attested") != new_attested:
        p4["attested"] = new_attested
        commit()


# ---------------------------------------------------------------------------
# Tab: Phase 5 — Risk
# ---------------------------------------------------------------------------

def tab_phase5() -> None:
    st.header("Phase 5 — Risk")
    _clear_phase_button("phase5")
    name = _ds_query_name()
    if not name:
        return
    _ds_name_banner(scope="p5")
    p5 = st.session_state["state"].setdefault("phase5", {})

    st.subheader("⚠️ P5.1 — Illicit exposure (90d)")
    if st.button("Run illicit exposure", key="run_p51"):
        df = run_query(Q.sql_illicit_exposure(name), "Illicit exposure", est_seconds=120, async_=True, max_wait=600)
        save_result("phase5", "illicit", df, label="Illicit exposure")
        if not df.empty:
            if "USD (in + out, 90d)" in df.columns:
                p5["illicit_total_usd"] = float(df["USD (in + out, 90d)"].sum())
            if "Severity Tier" in df.columns:
                p5["severe_categories"] = df.loc[
                    df["Severity Tier"].str.contains("SEVERE", na=False), "Category"
                ].tolist()
            commit()
        else:
            p5["illicit_total_usd"] = 0
            p5["severe_categories"] = []
            commit()
    df = render_saved("phase5", "illicit",
                      explain_empty="No high/severe-tier counterparty exposure in the 90-day window — either clean firm, or DS hasn't picked up the relevant counterparties.")
    if df is not None and not df.empty and "USD (in + out, 90d)" in df.columns:
        fig = px.bar(df, x="Category", y="USD (in + out, 90d)",
                     color="Severity Tier",
                     color_discrete_map={"🛑 SEVERE": FCA_DIVERGING["refuse"],
                                          "⚠️ HIGH": FCA_DIVERGING["warn"]},
                     title="Illicit exposure by category (90d)")
        fig.update_layout(font_family="Source Sans Pro", title_font_color=FCA_PURPLE,
                          plot_bgcolor="#fafafa")
        st.plotly_chart(fig, use_container_width=True)

    # --- P5.2 Monthly trend (#16)
    st.subheader("📉 P5.2 — Illicit exposure monthly trend (12 months)")
    if st.button("Run monthly trend", key="run_p52"):
        df = run_query(Q.sql_illicit_monthly_trend(name, months=12),
                       "Illicit monthly trend", est_seconds=120, async_=True, max_wait=600)
        save_result("phase5", "illicit_trend", df, label="Illicit monthly trend")
    df = render_saved("phase5", "illicit_trend")
    if df is not None and not df.empty and "Month" in df.columns:
        fig = px.line(df, x="Month", y="Illicit Exposure USD",
                      title=f"Monthly illicit exposure — {name}",
                      markers=True, color_discrete_sequence=[FCA_PURPLE])
        fig.update_layout(font_family="Source Sans Pro", title_font_color=FCA_PURPLE,
                          plot_bgcolor="#fafafa", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    # --- P5.4 Top illicit counterparties (named) (Top 4 #2)
    st.subheader("🏛️ P5.4 — Top illicit counterparties (named, 90d)")
    st.caption("The specific bad-actor entities the applicant has touched in 90 days. This is the table you cite in refusal notices.")
    if st.button("Run top illicit counterparties", key="run_p54"):
        df = run_query(Q.sql_top_illicit_counterparties(name, limit=25),
                       "Top illicit counterparties", est_seconds=120, async_=True, max_wait=600)
        save_result("phase5", "top_illicit", df, label="Top illicit counterparties")
    render_saved("phase5", "top_illicit",
                 explain_empty="No named high/severe-tier counterparty exposure in 90d.")
    render_counterparty_crosslinks("phase5", "top_illicit")

    # --- P5.6 Adverse-counterparty velocity (Tier 2 #5)
    st.subheader("🚀 P5.6 — Adverse-counterparty velocity (current 90d vs prior 90d)")
    st.caption("Is illicit exposure accelerating, stable, decelerating, new, or ended? Direction matters more than absolute number when applicants claim remediation.")
    if st.button("Run velocity check", key="run_p56"):
        df = run_query(Q.sql_adverse_velocity(name), "Adverse velocity", est_seconds=120, async_=True, max_wait=600)
        save_result("phase5", "velocity", df, label="Adverse velocity")
    render_saved("phase5", "velocity",
                 explain_empty="No high/severe-tier exposure in either quarter.")


# ---------------------------------------------------------------------------
# Tab: Phase 6 — Reserves
# ---------------------------------------------------------------------------

def tab_phase6() -> None:
    st.header("Phase 6 — Reserves")
    intake = st.session_state["state"]["intake"]
    p6 = st.session_state["state"].setdefault("phase6", {})
    st.subheader("💰 Stablecoin framing (declared)")
    bal = intake.get("declared_balance_usd")
    st.metric("Declared balance", fmt_usd(bal) if bal else "—")
    st.write(f"**Declared assets:** {intake.get('declared_assets') or '—'}")
    st.info("Reserves verification against issuer attestations is performed off-chain. "
            "On-chain balance is captured in the Phase 7 peer table.")
    if p6.get("declared_balance_usd") != bal:
        p6["declared_balance_usd"] = bal
        commit()


# ---------------------------------------------------------------------------
# Tab: Phase 7 — Peers
# ---------------------------------------------------------------------------

def tab_phase7() -> None:
    st.header("Phase 7 — Peers")
    _clear_phase_button("phase7")
    name = _ds_query_name()
    if not name:
        return
    intake = st.session_state["state"].get("intake", {})
    _ds_name_banner(scope="p7")
    p7 = st.session_state["state"].setdefault("phase7", {})
    peers = _peers_list()
    if not peers:
        st.warning("Add a comma-separated peer cohort in the sidebar intake.")
        return
    st.caption(f"Cohort: {', '.join(peers)} (substring-matched in DS — `Kraken` will match `Kraken.com`).")
    st.subheader("👥 P7.1 — Peer comparison")
    if st.button("Run peer comparison", key="run_p71"):
        df = run_query(Q.sql_peer_comparison(name, peers), "Peer comparison", est_seconds=120, async_=True, max_wait=600)
        save_result("phase7", "peer_table", df, label="Peer comparison")
        if not df.empty:
            p7["peer_table"] = df.to_dict(orient="records")
            commit()
    render_saved("phase7", "peer_table",
                 explain_empty="None of the cohort names matched any entities in cluster_summary.")


# ---------------------------------------------------------------------------
# Tab: Phase 8 — Decision
# ---------------------------------------------------------------------------

def tab_phase8() -> None:
    st.header("Phase 8 — Decision")
    p8 = st.session_state["state"].setdefault("phase8", {})
    outcome = p8.get("outcome", "Pending")
    outcome_class = (
        "outcome-pending" if outcome == "Pending"
        else "outcome-approve" if outcome.startswith("Approve")
        else "outcome-refuse" if outcome.startswith(("Refuse", "Minded"))
        else "outcome-other"
    )
    st.markdown(
        f"""<div class="decision-card">
          <h3>Current decision: <span class="{outcome_class}">{_h(outcome)}</span></h3>
          <p><strong>Analyst note:</strong> {_h(p8.get('analyst_note') or '—')}</p>
          <p><strong>Conditions:</strong> {_h(p8.get('conditions') or '—')}</p>
          <p><strong>Inconsistency challenge:</strong> {_h(p8.get('inconsistency_challenge') or '—')}</p>
          <p><strong>Second reviewer:</strong> {_h(p8.get('second_reviewer') or '—')}</p>
          <p><em>Decided at: {_h(p8.get('decided_at') or '—')}</em></p>
        </div>""",
        unsafe_allow_html=True,
    )
    with st.form("decision_form"):
        outcome_pick = st.selectbox("Outcome", DECISION_OUTCOMES,
            index=DECISION_OUTCOMES.index(p8.get("outcome", "Pending")))
        analyst_note = st.text_area("Analyst note", value=p8.get("analyst_note", ""), height=120)
        conditions = st.text_area("Conditions imposed (if approved)",
            value=p8.get("conditions", ""), height=80)
        inconsistency_challenge = st.text_area(
            "Declared-vs-observed inconsistency challenge raised with applicant",
            value=p8.get("inconsistency_challenge", ""), height=80)
        second_reviewer = st.text_input("Second reviewer (two-person sign-off)",
            value=p8.get("second_reviewer", ""))
        if st.form_submit_button("💾 Save decision"):
            p8.update({
                "outcome": outcome_pick, "analyst_note": analyst_note,
                "conditions": conditions,
                "inconsistency_challenge": inconsistency_challenge,
                "second_reviewer": second_reviewer,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            })
            commit()
            ds_data.log_audit(st.session_state["case_id"], "decision_saved",
                f"outcome={outcome_pick!r} reviewer={second_reviewer!r}")
            st.success("Decision saved.")
            st.rerun()


# ---------------------------------------------------------------------------
# Tab: Phase 9 — Handoff
# ---------------------------------------------------------------------------

def tab_phase9() -> None:
    st.header("Phase 9 — Handoff")
    p9 = st.session_state["state"].setdefault("phase9", {})

    st.subheader("🔁 Re-screening cadence")
    cadences = ["", "Monthly", "Quarterly", "Semi-annual", "Annual"]
    cadence = st.selectbox("Cadence", cadences,
        index=cadences.index(p9.get("rescreening_cadence", ""))
              if p9.get("rescreening_cadence") in cadences else 0)
    if cadence != p9.get("rescreening_cadence"):
        p9["rescreening_cadence"] = cadence
        commit()

    st.subheader("📤 Conditions handoff to Supervision")
    conditions = st.text_area("Conditions text to forward",
        value=p9.get("conditions_handoff", ""), height=100)
    if st.button("Save handoff text"):
        p9["conditions_handoff"] = conditions
        commit()
        st.success("Handoff text saved.")

    st.subheader("📄 Evidence pack export")
    if st.button("Generate evidence pack"):
        cid = st.session_state["case_id"]
        name = st.session_state["applicant_name"] or "Unnamed"
        audit = ds_data.get_audit_log(cid)
        blob, mime, fname = pdf_export.render_evidence_pack(
            cid, name, st.session_state["state"], audit_log=audit)
        st.download_button("⬇️ Download evidence pack",
            data=blob, file_name=fname, mime=mime)
        ds_data.log_audit(cid, "evidence_pack_generated", fname)


# ---------------------------------------------------------------------------
# Tab: Audit Log (#3)
# ---------------------------------------------------------------------------

def tab_audit() -> None:
    st.header("Audit Log")
    cid = st.session_state.get("case_id")
    if not cid:
        st.info("No case loaded.")
        return
    limit = st.slider("Entries to show (most recent first)",
                       min_value=50, max_value=5000, value=500, step=50,
                       key="_audit_limit")
    entries = ds_data.get_audit_log(cid, limit=limit)
    if not entries:
        st.info("No audit entries recorded yet.")
        return
    df = pd.DataFrame(entries)
    st.caption(f"{len(df)} audit entries for case `{cid}` (showing up to {limit}).")
    if len(df) == limit:
        st.info(f"Showing the most recent {limit} entries. Raise the slider to see more.")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Export audit log as CSV",
        data=csv, file_name=f"{cid}_audit.csv", mime="text/csv")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _case_header() -> None:
    """Branded header at the top of the main pane: case id, applicant name,
    regime, last-save time. Replaces the silent reliance on the sidebar
    case-id caption."""
    cid = st.session_state.get("case_id", "")
    if not cid:
        return
    intake = st.session_state.get("state", {}).get("intake", {}) or {}
    applicant = intake.get("applicant_name") or st.session_state.get("applicant_name") or "—"
    regime = intake.get("regime_applied_for") or "—"
    legal = intake.get("applicant_legal_entity") or ""
    st.markdown(
        f"""<div style="border-left: 6px solid {FCA_PURPLE};
             background: #faf6f8; padding: 0.7rem 1rem 0.6rem 1rem;
             margin: 0 0 1rem 0; border-radius: 4px;">
            <div style="font-size: 0.78rem; color: #888; letter-spacing: 0.06em;
                        text-transform: uppercase; margin-bottom: 0.2rem;">
                Case
            </div>
            <div style="display: flex; gap: 1.2rem; align-items: baseline;
                        flex-wrap: wrap;">
                <span style="font-size: 1.15rem; font-weight: 600;
                             color: {FCA_PURPLE}; font-family: monospace;">
                    {_htmllib.escape(cid)}
                </span>
                <span style="font-size: 1.05rem; font-weight: 500; color: #1a1a1a;">
                    {_htmllib.escape(applicant)}
                </span>
                <span style="font-size: 0.9rem; color: #666;">
                    {_htmllib.escape(legal) if legal else ""}
                </span>
                <span style="font-size: 0.85rem; color: #888; margin-left: auto;">
                    {_htmllib.escape(regime)}
                </span>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _demo_mode_badge() -> None:
    """Show a small badge at the top of the main pane when the loaded case
    was hydrated from snapshot fixtures (Demo Mode). Visible cue for the
    audience that the data is fixture, not live."""
    cid = st.session_state.get("case_id", "")
    if not cid.startswith("DEMO-"):
        return
    # Check that at least one phase has _results — i.e. fixtures were loaded
    state = st.session_state.get("state", {})
    has_results = any(
        (state.get(p, {}) or {}).get("_results")
        for p in ("phase0", "phase1", "phase2", "phase3", "phase5", "phase7")
    )
    if not has_results:
        return
    st.markdown(
        f"""<div style="background:#fff4e6; border:1px solid #f5b042;
             border-radius:6px; padding:0.4rem 0.9rem; margin-bottom:0.75rem;
             color:#7a3f00; font-size:0.92rem;">
        🎬 <strong>Demo Mode</strong> — phase results below are snapshot
        fixtures for the loaded demo case (<code>{cid}</code>). No live Data
        Solutions queries were made. Toggle off in sidebar → Load demo case
        to re-enable live queries.
        </div>""",
        unsafe_allow_html=True,
    )


def main() -> None:
    # FCA wordmark logo is ~3:1 aspect — squashed unreadably in a 16×16
    # browser-tab favicon slot. Use the flag emoji for the favicon; the
    # proper FCA logo lives at the top of the sidebar where it has room.
    favicon = "🇬🇧"
    st.set_page_config(
        page_title="UK FCA Firm Authorisation Workbench",
        page_icon=favicon,
        layout="wide",
    )
    apply_styles()
    init_session()
    ds_data.init_db()
    sidebar()
    _case_header()
    _demo_mode_badge()

    tabs = st.tabs([
        "Summary",
        "0. Triage",
        "1. Identity",
        "2. Verify",
        "3. Behaviour",
        "4. Controls",
        "5. Risk",
        "6. Reserves",
        "7. Peers",
        "8. Decision",
        "9. Handoff",
        "Audit log",
    ])
    with tabs[0]: tab_case_summary()
    with tabs[1]: tab_phase0()
    with tabs[2]: tab_phase1()
    with tabs[3]: tab_phase2()
    with tabs[4]: tab_phase3()
    with tabs[5]: tab_phase4()
    with tabs[6]: tab_phase5()
    with tabs[7]: tab_phase6()
    with tabs[8]: tab_phase7()
    with tabs[9]: tab_phase8()
    with tabs[10]: tab_phase9()
    with tabs[11]: tab_audit()


if __name__ == "__main__":
    main()
