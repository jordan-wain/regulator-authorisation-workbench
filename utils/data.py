"""
Data layer for the UK FCA Firm Authorisation Workbench.

Provides:
  - Chainalysis Data Solutions SQL execution (with Streamlit caching)
  - Case persistence via SQLite
  - Companies House company search & PSC lookup
  - FCA register / warning-list checks (via DS entity data)
  - Evidence-pack generation
"""

import os
import json
import sqlite3
import datetime

import requests
import pandas as pd
import streamlit as st

# ── API Keys ───────────────────────────────────────────────────────────
# Check env vars first, fall back to Streamlit secrets (for Cloud deployment).
DS_API_KEY = os.environ.get("DATA_SOLUTIONS_API_KEY") or st.secrets.get("DATA_SOLUTIONS_API_KEY", "")
CH_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY") or st.secrets.get("COMPANIES_HOUSE_API_KEY", "")

# ── Endpoints ──────────────────────────────────────────────────────────
DS_BASE = os.environ.get(
    "DATA_SOLUTIONS_API_BASE_URL",
    st.secrets.get("DATA_SOLUTIONS_API_BASE_URL",
                   "https://api.chainalysis.com/api/datasets/v2"),
)
CH_BASE = "https://api.company-information.service.gov.uk"


# ── Helpers ────────────────────────────────────────────────────────────

def esc(value: str) -> str:
    """Escape a value for inclusion in a SQL string literal."""
    return value.replace("'", "''")


# ── Data Solutions ─────────────────────────────────────────────────────

def ds_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query against Chainalysis Data Solutions (raw)."""
    resp = requests.post(
        f"{DS_BASE}/query",
        headers={"Token": DS_API_KEY, "Content-Type": "application/json"},
        json={"query": sql},
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("results", payload if isinstance(payload, list) else [])
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300, show_spinner="Querying Data Solutions …")
def ds_query_cached(sql: str) -> pd.DataFrame:
    """Cached wrapper around ds_query (5-minute TTL)."""
    return ds_query(sql)


# ── Case Persistence (SQLite) ─────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cases.db")


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cases (
               case_id    TEXT PRIMARY KEY,
               data       TEXT NOT NULL,
               updated_at TEXT NOT NULL
           )"""
    )
    conn.commit()
    return conn


def save_case(case_id: str, data: dict) -> None:
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO cases VALUES (?, ?, ?)",
        (case_id, json.dumps(data, default=str), datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def load_case(case_id: str) -> dict | None:
    conn = _db()
    row = conn.execute("SELECT data FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def list_cases() -> list[str]:
    conn = _db()
    rows = conn.execute("SELECT case_id FROM cases ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Companies House ───────────────────────────────────────────────────

def ch_search(query: str) -> list[dict]:
    """Search Companies House for companies matching *query*."""
    r = requests.get(
        f"{CH_BASE}/search/companies",
        params={"q": query, "items_per_page": 10},
        auth=(CH_API_KEY, ""),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("items", [])


def ch_psc(company_number: str) -> list[dict]:
    """Return Persons with Significant Control for a company."""
    r = requests.get(
        f"{CH_BASE}/company/{company_number}/persons-with-significant-control",
        auth=(CH_API_KEY, ""),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("items", [])


# ── FCA Register / Warnings (via DS entity data) ─────────────────────

def check_fca_register(name: str) -> pd.DataFrame:
    """Check whether *name* appears in DS entity data (perimeter check)."""
    sql = f"""
    SELECT DISTINCT entity_name, entity_category
    FROM utils.entities
    WHERE entity_name ILIKE '%{esc(name)}%'
    LIMIT 20
    """
    return ds_query_cached(sql)


def check_fca_warnings(name: str) -> pd.DataFrame:
    """Check whether *name* matches a high-risk / warning-list category."""
    sql = f"""
    SELECT DISTINCT entity_name, entity_category
    FROM utils.entities
    WHERE entity_name ILIKE '%{esc(name)}%'
      AND entity_category IN (
          'scam', 'fraud shop', 'ponzi scheme',
          'fake exchange', 'phishing', 'terrorist financing'
      )
    LIMIT 20
    """
    return ds_query_cached(sql)


# ── Evidence Pack ─────────────────────────────────────────────────────

def generate_evidence_pack_bytes(case_data: dict) -> bytes:
    """Serialise the full case record as a downloadable JSON evidence pack."""
    pack = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "workbench_version": "1.0.0",
        "case": case_data,
    }
    return json.dumps(pack, indent=2, default=str).encode("utf-8")
