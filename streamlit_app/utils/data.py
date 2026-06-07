"""Data layer for the Firm Authorisation Workbench Streamlit app.

Three responsibilities:

1. Data Solutions analytical SQL queries (synchronous, via HTTP).
2. Companies House PSC + officers lookups (UK incorporation data).
3. Per-case state persistence in a local SQLite DB, plus an audit log.

Also bundles the two FCA reference lists (registered firms and unauthorised
warnings) so they can be cross-checked offline without hitting the DS API.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DS_BASE_URL = os.environ.get(
    "DATA_SOLUTIONS_BASE_URL",
    "https://api.transpose.io",
).rstrip("/")
DS_SQL_PATH = "/sql/analytical"

DS_API_KEY = os.environ.get("DATA_SOLUTIONS_API_KEY") or st.secrets.get("DATA_SOLUTIONS_API_KEY", "")
COMPANIES_HOUSE_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY") or st.secrets.get("COMPANIES_HOUSE_API_KEY", "")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cases.db"


# ---------------------------------------------------------------------------
# Data Solutions
# ---------------------------------------------------------------------------

class DataSolutionsError(RuntimeError):
    pass


def run_ds_query(sql: str, timeout: int = 300) -> pd.DataFrame:
    """Execute a SQL query against the DS analytical endpoint, return a DataFrame.

    Raises DataSolutionsError on any non-2xx or error payload. Empty result
    sets return an empty DataFrame (with no columns).
    """
    if not DS_API_KEY:
        raise DataSolutionsError(
            "DATA_SOLUTIONS_API_KEY env var is not set — cannot reach Data Solutions"
        )

    url = DS_BASE_URL + DS_SQL_PATH
    headers = {
        "X-Api-Key": DS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.post(url, headers=headers, json={"sql": sql}, timeout=timeout)
    if resp.status_code >= 400:
        raise DataSolutionsError(
            f"DS HTTP {resp.status_code}: {resp.text[:500]}"
        )
    try:
        payload = resp.json()
    except ValueError as e:
        raise DataSolutionsError(f"DS returned non-JSON body: {resp.text[:200]}") from e

    if isinstance(payload, dict) and payload.get("status") == "error":
        raise DataSolutionsError(f"DS error: {payload.get('error') or payload}")

    # Conventional shape: {"results": [ {col: val, ...}, ... ], "stats": {...}}
    rows = (
        payload.get("results")
        if isinstance(payload, dict)
        else payload
    )
    if rows is None:
        rows = []
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Async query path — for queries that exceed the synchronous timeout
# ---------------------------------------------------------------------------

def _ds_headers() -> dict:
    if not DS_API_KEY:
        raise DataSolutionsError(
            "DATA_SOLUTIONS_API_KEY env var is not set — cannot reach Data Solutions"
        )
    return {
        "X-Api-Key": DS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def run_ds_query_async(
    sql: str,
    max_wait: float = 600.0,
    poll_interval: float = 3.0,
    progress_cb=None,
) -> pd.DataFrame:
    """Submit a SQL query asynchronously, poll until done, return a DataFrame.

    Use this for queries that may exceed the ~120s synchronous limit. Polls
    every `poll_interval` seconds up to `max_wait` total. If `progress_cb` is
    provided, it's called as ``progress_cb(elapsed_seconds, status_text)``
    each poll so the caller can update a Streamlit status widget.
    """
    headers = _ds_headers()
    # 1) Submit
    submit_url = DS_BASE_URL + "/sql/analytical/async"
    resp = requests.post(submit_url, headers=headers, json={"sql": sql}, timeout=30)
    if resp.status_code >= 400:
        raise DataSolutionsError(f"DS async submit HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        body = resp.json()
    except ValueError as e:
        raise DataSolutionsError(f"DS async submit returned non-JSON: {resp.text[:200]}") from e
    query_id = body.get("query_id") or body.get("id")
    if not query_id:
        raise DataSolutionsError(f"DS async submit missing query_id: {body}")

    # 2) Poll. NOTE: query_id is a *query parameter*, not a URL path segment.
    status_url = DS_BASE_URL + "/sql/analytical/status"
    t0 = time.monotonic()
    while True:
        elapsed = time.monotonic() - t0
        if elapsed > max_wait:
            raise DataSolutionsError(
                f"DS async query timed out after {int(elapsed)}s (max_wait={int(max_wait)}). "
                "Consider raising max_wait or narrowing the query."
            )
        try:
            sresp = requests.get(status_url, headers=headers,
                                 params={"query_id": query_id}, timeout=30)
        except requests.exceptions.RequestException as e:
            raise DataSolutionsError(f"DS async poll failed: {e}") from e
        if sresp.status_code >= 400:
            raise DataSolutionsError(
                f"DS async poll HTTP {sresp.status_code}: {sresp.text[:500]}"
            )
        try:
            sbody = sresp.json()
        except ValueError as e:
            raise DataSolutionsError(
                f"DS async poll returned non-JSON: {sresp.text[:200]}"
            ) from e
        status = (sbody.get("status") or "").lower()
        if progress_cb:
            try:
                progress_cb(elapsed, status or "polling")
            except Exception:
                pass
        if status == "success":
            rows = sbody.get("results") or []
            return pd.DataFrame(rows)
        if status == "error":
            raise DataSolutionsError(
                f"DS async error: {sbody.get('error') or sbody.get('message') or sbody}"
            )
        # status == "pending" (or anything else) → sleep and re-poll
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Companies House
# ---------------------------------------------------------------------------

CH_BASE_URL = "https://api.company-information.service.gov.uk"


class CompaniesHouseError(RuntimeError):
    pass


def _ch_get(path: str, params: dict | None = None) -> dict:
    if not COMPANIES_HOUSE_API_KEY:
        raise CompaniesHouseError(
            "COMPANIES_HOUSE_API_KEY env var is not set — cannot reach Companies House"
        )
    url = CH_BASE_URL + path
    resp = requests.get(
        url,
        params=params or {},
        auth=(COMPANIES_HOUSE_API_KEY, ""),
        timeout=30,
    )
    if resp.status_code == 404:
        return {}
    if resp.status_code >= 400:
        raise CompaniesHouseError(f"CH HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def clean_company_name(name: str) -> str:
    """Strip common TLDs and trailing punctuation so a trading name like
    'Coinbase.com' or 'kraken.co.uk' can be sent to Companies House search."""
    if not name:
        return ""
    n = name.strip()
    # Strip well-known TLD suffixes (longest first to avoid partial matches)
    for tld in (
        ".co.uk", ".com", ".net", ".io", ".org", ".global",
        ".exchange", ".finance", ".app", ".xyz",
    ):
        if n.lower().endswith(tld):
            n = n[: -len(tld)]
            break
    return n.strip().strip(".").strip()


def ch_search_company(name: str, items_per_page: int = 10) -> list[dict]:
    """Search Companies House for a company by name."""
    if not name.strip():
        return []
    res = _ch_get(
        "/search/companies",
        params={"q": name.strip(), "items_per_page": items_per_page},
    )
    return res.get("items", [])


def ch_get_psc(company_number: str) -> list[dict]:
    """Fetch PSCs (persons with significant control) for a UK company number."""
    res = _ch_get(f"/company/{company_number}/persons-with-significant-control")
    return res.get("items", [])


def ch_get_officers(company_number: str) -> list[dict]:
    """Fetch the company officers list (used for MLRO cross-check)."""
    res = _ch_get(f"/company/{company_number}/officers")
    return res.get("items", [])


def _summarise_candidate(item: dict) -> dict:
    return {
        "company_number": item.get("company_number"),
        "title": item.get("title"),
        "company_status": item.get("company_status"),
        "date_of_creation": item.get("date_of_creation"),
        "address_snippet": item.get("address_snippet"),
    }


def companies_house_search_candidates(
    legal_entity: str = "",
    trading_name: str = "",
    include_dissolved: bool = False,
    limit: int = 10,
) -> dict:
    """Search Companies House and return all candidates for the case officer to pick.

    Prefers ``legal_entity`` when present (because it is the registered name),
    falls back to ``trading_name`` with TLD suffixes stripped.

    Returns:
        {
            "queried_name": <name actually sent to CH>,
            "candidates": [ {company_number, title, status, ...}, ... ],
            "queried_at": ISO timestamp,
            "error": optional str,
        }
    """
    raw = legal_entity.strip() if legal_entity and legal_entity.strip() else trading_name
    name = clean_company_name(raw)
    out: dict[str, Any] = {
        "queried_name": name,
        "raw_input": raw,
        "source_field": "legal_entity" if legal_entity and legal_entity.strip() else "trading_name",
        "candidates": [],
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }
    if not name:
        out["error"] = "No name to search (legal entity and trading name both empty)"
        return out
    try:
        hits = ch_search_company(name, items_per_page=limit)
        if not include_dissolved:
            hits = [h for h in hits if (h.get("company_status") or "").lower() != "dissolved"]
        if not hits:
            out["error"] = (
                f"No Companies House match for '{name}'"
                + ("" if include_dissolved else " (active companies only — tick 'include dissolved' to widen)")
            )
            return out
        out["candidates"] = [_summarise_candidate(h) for h in hits]
    except CompaniesHouseError as e:
        out["error"] = str(e)
    return out


def companies_house_fetch_company(company_number: str) -> dict:
    """Fetch full PSC + officers for a specific company number."""
    out: dict[str, Any] = {
        "company_number": company_number,
        "psc": [],
        "officers": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        out["psc"] = ch_get_psc(company_number)
        out["officers"] = ch_get_officers(company_number)
    except CompaniesHouseError as e:
        out["error"] = str(e)
    return out


def companies_house_lookup(applicant_name: str) -> dict:
    """Back-compat shim: single-name search → first non-dissolved hit → PSC + officers.

    Prefer ``companies_house_search_candidates`` + ``companies_house_fetch_company``
    for new code so the case officer can choose between multiple legal entities.
    """
    search = companies_house_search_candidates(trading_name=applicant_name)
    out: dict[str, Any] = {
        "queried_name": search["queried_name"],
        "company": None,
        "psc": [],
        "officers": [],
        "queried_at": search["queried_at"],
    }
    if search.get("error"):
        out["error"] = search["error"]
        return out
    candidates = search.get("candidates") or []
    if not candidates:
        out["error"] = "No Companies House match"
        return out
    top = candidates[0]
    out["company"] = top
    cn = top.get("company_number")
    if cn:
        full = companies_house_fetch_company(cn)
        out["psc"] = full.get("psc", [])
        out["officers"] = full.get("officers", [])
        if full.get("error"):
            out["error"] = full["error"]
    return out


# ---------------------------------------------------------------------------
# FCA reference lists (mirror of scripts/build_phase0_uk.py — kept in sync)
# ---------------------------------------------------------------------------

FCA_REGISTERED: list[str] = [
    "Coinbase", "Coinbase.com",
    "eToro", "eToro.com",
    "Kraken", "Kraken.com",
    "Gemini", "Gemini.com",
    "Bitstamp", "Bitstamp.net",
    "Revolut", "Revolut.com",
    "CoinJar", "CoinJar.com",
    "Bitpanda", "Bitpanda.com",
    "Uphold", "Uphold.com",
    "Crypto.com", "Crypto.com Exchange",
    "Archax", "Archax.com",
    "CoinCorner.com",
    "Coinpass.com",
    "Coinfloor.co.uk",
    "Bittylicious.com",
    "Solidi.co",
    "BottlePay.com",
    "CoinBurp.com",
    "BitcoinPoint.com",
    "Tap.global",
    "Banx.io",
    "CEX.IO", "CEX.IO.com",
    "LMAX Digital",
    "PayPal", "PayPal.com",
    "Zodia Custody",
    "Ziglu",
    "Wintermute",
    "Galaxy Digital",
    "Copper.co",
    "Blockchain.com",
    "Paysafe",
    "Stripe",
    "Circle",
    "Bitfinex", "Bitfinex.com",
    "OKX", "OKX.com",
]


FCA_WARNINGS: list[str] = [
    "Bitcoin Loophole",
    "Bitcoin News Trader",
    "Crypto Engine",
    "British Bitcoin Profits",
    "Marketing4You.Tech",
    "TradeFX TradingBot",
    "Coinfalcon Limited",
    "London Bitcoin Exchange Ltd",
    "Cryptonex LP",
    "BitOnyx Labs",
    "The Centric Corp Ltd",
    "Oryxian",
    "Cryptonomy Finance",
    "Orbios",
    "ABRAHAM ELITE LTD",
]


def _name_match(needle: str, haystack: str) -> bool:
    n = needle.strip().lower()
    h = haystack.strip().lower()
    if not n or not h:
        return False
    return n in h or h in n


def check_fca_register(applicant: str) -> dict:
    """Bidirectional substring match against the FCA Cryptoasset Firms register."""
    matches = [name for name in FCA_REGISTERED if _name_match(applicant, name)]
    return {
        "registered": bool(matches),
        "matches": matches,
        "register_size": len(FCA_REGISTERED),
    }


def check_fca_warnings(applicant: str) -> dict:
    """Bidirectional substring match against the FCA unauthorised-firms warning list."""
    hits = [name for name in FCA_WARNINGS if _name_match(applicant, name)]
    return {
        "warning_hit": bool(hits),
        "matches": hits,
        "warning_list_size": len(FCA_WARNINGS),
    }


# ---------------------------------------------------------------------------
# SQLite case state
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id        TEXT PRIMARY KEY,
                applicant_name TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                state_json     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id    TEXT NOT NULL,
                action     TEXT NOT NULL,
                detail     TEXT,
                timestamp  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);
            """
        )
        conn.commit()


def list_cases() -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT case_id, applicant_name, created_at, updated_at "
            "FROM cases ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def load_case(case_id: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["state"] = json.loads(out.pop("state_json"))
    except json.JSONDecodeError:
        out["state"] = {}
    return out


def save_case(case_id: str, applicant_name: str, state: dict) -> None:
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(state, default=str)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE cases SET applicant_name = ?, updated_at = ?, state_json = ? "
                "WHERE case_id = ?",
                (applicant_name, now, payload, case_id),
            )
        else:
            conn.execute(
                "INSERT INTO cases (case_id, applicant_name, created_at, updated_at, state_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (case_id, applicant_name, now, now, payload),
            )
        conn.commit()
    log_audit(case_id, "save_case", f"saved state with {len(state)} keys")


def delete_case(case_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        conn.commit()
    log_audit(case_id, "delete_case", "case deleted")


def rename_case(old_case_id: str, new_case_id: str) -> None:
    """Re-key a case in both `cases` and `audit_log` tables atomically.

    Raises ValueError if the new id already exists (so we don't merge two cases
    silently). Logs the rename to the audit_log under the *new* id.
    """
    init_db()
    if old_case_id == new_case_id:
        return
    with _connect() as conn:
        existing = conn.execute(
            "SELECT case_id FROM cases WHERE case_id = ?", (new_case_id,)
        ).fetchone()
        if existing:
            raise ValueError(f"Case id {new_case_id!r} already exists")
        conn.execute("UPDATE cases SET case_id = ?, updated_at = ? WHERE case_id = ?",
                     (new_case_id, datetime.now(timezone.utc).isoformat(), old_case_id))
        conn.execute("UPDATE audit_log SET case_id = ? WHERE case_id = ?",
                     (new_case_id, old_case_id))
        conn.commit()
    log_audit(new_case_id, "rename_case", f"{old_case_id} -> {new_case_id}")


def log_audit(case_id: str, action: str, detail: str | None = None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (case_id, action, detail, timestamp) VALUES (?, ?, ?, ?)",
            (case_id, action, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_audit_log(case_id: str, limit: int = 200) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT timestamp, action, detail FROM audit_log "
            "WHERE case_id = ? ORDER BY id DESC LIMIT ?",
            (case_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Companies House PII redaction (#E)
# ---------------------------------------------------------------------------

_PII_KEYS_TO_REDACT = {
    "date_of_birth", "address_line_1", "address_line_2",
    "premises", "postal_code", "locality", "region",
}


def _redact_obj(obj):
    """Recursively replace PII fields with '[redacted]'. Keeps the key so
    consumers know the field existed but doesn't persist personal data."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _PII_KEYS_TO_REDACT:
                out[k] = "[redacted]"
            else:
                out[k] = _redact_obj(v)
        return out
    if isinstance(obj, list):
        return [_redact_obj(x) for x in obj]
    return obj


def redact_ch_pii(ch_payload: dict) -> dict:
    """Strip PSC/officer DOB + home-address fields from a Companies House payload
    before persisting to SQLite. Identity / role / appointment dates are kept,
    which is what a regulator's evidence pack needs."""
    if not isinstance(ch_payload, dict):
        return ch_payload
    out = dict(ch_payload)
    for k in ("psc", "officers"):
        if k in out:
            out[k] = _redact_obj(out[k])
    return out
