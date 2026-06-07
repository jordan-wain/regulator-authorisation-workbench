"""SQL queries used by the Streamlit Firm Authorisation Workbench.

Each function returns a fully-formed SQL string with parameters substituted
inline (as quoted literals) so the result can be sent directly to the
Data Solutions SQL endpoint without template-tag processing.

These queries are direct ports of the cards on Data Solutions dashboard 4015
(see scripts/build_phase*_uk.py). They use the same `cross_chain.*` schema and
include the `asset_id IN (SELECT asset_id FROM utils.assets)` filter to drop
mispriced tokens, consistent with build_conventions.md §3.

IMPORTANT — name matching:
The exact-equality match in dashboard 4015 only worked because the dashboard
parameter held the *full* entity_name as stored in DS (e.g. 'Coinbase.com').
A regulator typing a trading name into the app may enter 'Coinbase' instead.
All queries here use a *bidirectional substring match* (see name_match_cte)
so 'Coinbase' matches 'Coinbase.com' and vice-versa. Tradeoff: an applicant
name that is a substring of an unrelated entity (e.g. 'Bit' matches both
'Bitstamp' and 'Bitfinex') will return broader results — for the regulator
use case that's actually preferable to silent zero-result queries.
"""
from __future__ import annotations

from typing import Iterable


# ---------------------------------------------------------------------------
# Literal helpers
# ---------------------------------------------------------------------------

def q(s: str | None) -> str:
    """SQL-quote a string literal (None -> NULL)."""
    if s is None:
        return "NULL"
    return "'" + str(s).replace("'", "''") + "'"


def values_list(items: Iterable[str], col: str = "entity_name") -> str:
    """Build a `(VALUES ('a'),('b')) AS t(col)` block."""
    items = [i for i in items if i]
    if not items:
        return f"(SELECT CAST(NULL AS STRING) AS {col} WHERE 1=0)"
    rows = ",".join(f"({q(i)})" for i in items)
    return f"(VALUES {rows}) AS t({col})"


def lowered_address_values(addresses: Iterable[str]) -> str:
    """Build a `(VALUES (lower('0x..')), ...) AS t(address)` block."""
    addresses = [a.strip() for a in addresses if a and a.strip()]
    if not addresses:
        return "(SELECT CAST(NULL AS STRING) AS address WHERE 1=0)"
    rows = ",".join(f"(LOWER({q(a)}))" for a in addresses)
    return f"(VALUES {rows}) AS t(address)"


def name_match(name_col: str, applicant: str) -> str:
    """Return SQL boolean expression matching ``name_col`` against ``applicant``.

    Performance note (the bidirectional ``instr()`` version of this used to scan
    the entire table for every query — 60-90s for Coinbase). This version is
    designed for Spark **predicate pushdown** / data-skipping:

      1. Exact equality on the raw input
      2. Exact equality on common trading-name variants (.com / .co.uk / .net /
         .io stripped or added)
      3. ``LOWER(col) LIKE 'foo%'`` — anchored prefix LIKE, which Spark CAN push
         down (unlike `'%foo%'` which forces a scan)

    Trade-off vs the old fuzzy match: this misses cases where the DS name is
    a *substring* of the applicant input (e.g. user types 'Coinbase Inc' but
    DS has 'Coinbase'). For the regulator use case that's a fair trade — we
    get 10x faster queries, and the user can fall back to the toggle in the
    sidebar Settings (Trading name <-> Legal entity) if both fail.
    """
    a_raw = (applicant or "").strip()
    if not a_raw:
        return "1=0"

    # Build the candidate set: raw input plus common-variant transforms.
    base = a_raw
    base_lower = a_raw.lower()
    variants = {a_raw}
    # If user typed 'Coinbase.com', also try 'Coinbase' (strip TLD)
    for tld in (".com", ".co.uk", ".net", ".io", ".org", ".global",
                ".exchange", ".finance", ".app", ".xyz"):
        if base_lower.endswith(tld):
            variants.add(base[: -len(tld)])
            break
    # If user typed 'Coinbase' (no TLD), also try common TLD additions
    if "." not in base_lower:
        for tld in (".com", ".co.uk", ".io", ".net"):
            variants.add(base + tld)

    # Exact-equality clauses (cheap, indexable)
    exact_clauses = [f"LOWER({name_col}) = LOWER({q(v)})" for v in sorted(variants)]

    # Prefix LIKE on the bare (TLD-stripped) name — Spark pushes this down too.
    bare = base
    for tld in (".com", ".co.uk", ".net", ".io", ".org"):
        if bare.lower().endswith(tld):
            bare = bare[: -len(tld)]
            break
    # Escape SQL-LIKE special chars in the prefix
    bare_escaped = bare.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    prefix_clause = (
        f"LOWER({name_col}) LIKE LOWER({q(bare_escaped + '%')}) ESCAPE '\\\\'"
    )

    return "(" + " OR ".join(exact_clauses + [prefix_clause]) + ")"


# ---------------------------------------------------------------------------
# Phase 0 — Triage
# ---------------------------------------------------------------------------

def sql_perimeter_check(applicant: str, fca_registered: list[str]) -> str:
    """C4 — Perimeter pre-check: FCA register + UK geo signal three-state."""
    reg = values_list(fca_registered, col="entity_name")
    return f"""
WITH fca_registered AS (SELECT entity_name FROM {reg}),
gb_signal AS (
  SELECT primary_country_confidence_level
  FROM cross_chain.geo_signals_named_entities_primary_country
  WHERE {name_match("entity_name", applicant)}
    AND primary_country_of_operation_code = 'GB'
),
register_status AS (
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM fca_registered fr
    WHERE instr(LOWER({q(applicant)}), LOWER(fr.entity_name)) > 0
       OR instr(LOWER(fr.entity_name), LOWER({q(applicant)})) > 0
  ) THEN 'licensed' ELSE 'unlicensed' END AS reg_status
)
SELECT
  CASE
    WHEN (SELECT reg_status FROM register_status) = 'licensed'
      THEN '✅ On FCA register'
    WHEN (SELECT reg_status FROM register_status) = 'unlicensed'
         AND EXISTS (SELECT 1 FROM gb_signal)
      THEN '🛑 PERIMETER HIT — primary-UK, not on FCA register'
    ELSE '🟡 Not on FCA register, no primary-UK signal'
  END AS `Perimeter Status`,
  (SELECT reg_status FROM register_status) AS `Register Status`,
  COALESCE((SELECT primary_country_confidence_level FROM gb_signal), 'no signal')
    AS `UK Confidence`
"""


def sql_sanctions_screen(declared_wallets: list[str]) -> str:
    """C5 — Sanctions / severity screen on declared wallets (worst-wins per row)."""
    dw = lowered_address_values(declared_wallets)
    return f"""
WITH declared_wallets AS (SELECT address FROM {dw})
SELECT
  dw.address AS `Declared Address`,
  COALESCE(c.entity_name, '— unattributed') AS `Entity (if attributed)`,
  COALESCE(c.entity_category, '—') AS `Category`,
  COALESCE(ec.severity, 'clear') AS `Severity`,
  c.prior_entity_category AS `Prior Category`,
  c.entity_category_changed_at AS `Category Changed At`,
  c.chain_name AS `Chain`,
  CASE WHEN ec.severity = 'severe' THEN '🛑 SEVERE HIT'
       WHEN ec.severity = 'high'   THEN '⚠️ High-risk hit'
       ELSE '✅ Clear'
  END AS `Screen Result`
FROM declared_wallets dw
LEFT JOIN cross_chain.clusters c ON c.address = dw.address
LEFT JOIN utils.entity_categories ec ON c.entity_category = ec.entity_category
ORDER BY
  CASE ec.severity WHEN 'severe' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
  dw.address
"""


def sql_risk_tier(applicant: str, fca_registered: list[str]) -> str:
    """C8 — Triage Risk Tier (Standard / Enhanced / Intensive)."""
    reg = values_list(fca_registered, col="entity_name")
    return f"""
WITH fca_registered AS (SELECT entity_name FROM {reg}),
applicant_activity AS (
  SELECT SUM(received_usd) AS total_received_usd, MAX(last) AS last_activity
  FROM cross_chain.cluster_summary
  WHERE {name_match("entity_name", applicant)}
),
gb_signal AS (
  SELECT primary_country_confidence_level
  FROM cross_chain.geo_signals_named_entities_primary_country
  WHERE {name_match("entity_name", applicant)}
    AND primary_country_of_operation_code = 'GB'
),
register_status AS (
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM fca_registered fr
    WHERE instr(LOWER({q(applicant)}), LOWER(fr.entity_name)) > 0
       OR instr(LOWER(fr.entity_name), LOWER({q(applicant)})) > 0
  ) THEN 'licensed' ELSE 'unlicensed' END AS reg_status
)
SELECT
  CASE
    WHEN (SELECT reg_status FROM register_status) = 'unlicensed'
         AND EXISTS (SELECT 1 FROM gb_signal)
      THEN '🚨 Intensive (perimeter trigger)'
    WHEN (SELECT total_received_usd FROM applicant_activity) >= 1e10
      THEN '🟠 Intensive (size trigger)'
    WHEN (SELECT total_received_usd FROM applicant_activity) >= 1e9
      THEN '🟡 Enhanced (size trigger)'
    ELSE '🟢 Standard'
  END AS `Risk Tier`,
  (SELECT total_received_usd FROM applicant_activity) AS `Total Received USD`,
  (SELECT reg_status FROM register_status) AS `FCA Register Status`,
  COALESCE((SELECT primary_country_confidence_level FROM gb_signal), 'No primary-GB signal') AS `UK Confidence`
"""


# ---------------------------------------------------------------------------
# Phase 1 — Identity
# ---------------------------------------------------------------------------

def sql_time_on_chain(applicant: str) -> str:
    """P1.2 — First/last seen and maturity tier."""
    return f"""
WITH activity AS (
  SELECT MIN(first) AS first_seen, MAX(last) AS last_seen
  FROM cross_chain.cluster_summary
  WHERE {name_match("entity_name", applicant)}
)
SELECT
  first_seen AS `First Observed`,
  last_seen AS `Last Observed`,
  DATEDIFF(last_seen, first_seen) AS `Days On Chain`,
  DATEDIFF(CURRENT_DATE(), last_seen) AS `Days Since Last Active`,
  CASE
    WHEN DATEDIFF(last_seen, first_seen) >= 1825 THEN '🟢 5+ years on chain — established'
    WHEN DATEDIFF(last_seen, first_seen) >= 365 THEN '🟡 1–5 years on chain — moderate history'
    WHEN DATEDIFF(last_seen, first_seen) >= 90  THEN '🟠 90 days–1 year on chain — short history'
    WHEN first_seen IS NULL THEN '— no activity data'
    ELSE '🔴 <90 days on chain — very new'
  END AS `Maturity Signal`
FROM activity
"""


def sql_osint(applicant: str, declared_wallets: list[str]) -> str:
    """P1.5 — Third-party OSINT/adverse-media hits across applicant cluster + declared wallets.
    Returns aggregated counts per source."""
    if declared_wallets:
        wallet_union = "UNION SELECT address FROM " + lowered_address_values(declared_wallets)
    else:
        wallet_union = ""
    return f"""
WITH applicant_clusters AS (
  SELECT DISTINCT cluster_id FROM cross_chain.clusters
  WHERE {name_match("entity_name", applicant)}
),
applicant_addresses AS (
  SELECT DISTINCT address FROM cross_chain.clusters
  WHERE cluster_id IN (SELECT cluster_id FROM applicant_clusters)
),
target_addresses AS (
  SELECT address FROM applicant_addresses
  {wallet_union}
),
hits AS (
  SELECT source, COUNT(*) AS findings, MIN(timestamp) AS earliest, MAX(timestamp) AS latest
  FROM cross_chain.third_party_osint
  WHERE address IN (SELECT address FROM target_addresses)
  GROUP BY source
)
SELECT
  source AS `OSINT Source`,
  findings AS `Findings`,
  earliest AS `Earliest`,
  latest AS `Latest`,
  CASE
    WHEN source IN ('shapeshift.io', 'cloudburst', 'blockchain.info') THEN '🟢 High-quality attribution source'
    WHEN source IN ('bitcoin_abuse', 'consumer_complaints', 'flashpoint', 'gemini advisory data') THEN '⚠️ Adverse-signal source'
    WHEN source LIKE '%comment%' OR source LIKE '%talk%' THEN '🟡 Social-media source (low confidence)'
    ELSE '📝 Other'
  END AS `Source Quality`
FROM hits
ORDER BY findings DESC LIMIT 25
"""


def sql_osint_details(applicant: str, declared_wallets: list[str], limit: int = 50) -> str:
    """P1.5b — Drill-down rows: actual OSINT findings (address, source, text, timestamp)."""
    if declared_wallets:
        wallet_union = "UNION SELECT address FROM " + lowered_address_values(declared_wallets)
    else:
        wallet_union = ""
    return f"""
WITH applicant_clusters AS (
  SELECT DISTINCT cluster_id FROM cross_chain.clusters
  WHERE {name_match("entity_name", applicant)}
),
applicant_addresses AS (
  SELECT DISTINCT address FROM cross_chain.clusters
  WHERE cluster_id IN (SELECT cluster_id FROM applicant_clusters)
),
target_addresses AS (
  SELECT address FROM applicant_addresses
  {wallet_union}
)
SELECT
  address  AS `Address`,
  source   AS `Source`,
  text     AS `Finding`,
  timestamp AS `Observed`
FROM cross_chain.third_party_osint
WHERE address IN (SELECT address FROM target_addresses)
ORDER BY timestamp DESC NULLS LAST
LIMIT {int(limit)}
"""


# ---------------------------------------------------------------------------
# Phase 2 — Verify / Volume reconciliation
# ---------------------------------------------------------------------------

def sql_volume_reconciliation(
    applicant: str, window_days: int, declared_volume_usd: str | None = None
) -> str:
    """P2.1 — Inflow + outflow vs declared volume (status banding identical to dashboard)."""
    # try_cast() returns NULL on bad input rather than throwing — so an applicant
    # who types '5B', 'five billion' or '$5,000,000,000' degrades to '📥 Awaiting
    # input' status rather than crashing the whole volume tile.
    declared = "NULL" if declared_volume_usd in (None, "") else f"try_cast({q(declared_volume_usd)} AS DOUBLE)"
    return f"""
WITH inflow AS (
  SELECT SUM(amount_usd_total) AS in_usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({window_days} AS INT))
),
outflow AS (
  SELECT SUM(amount_usd_total) AS out_usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({window_days} AS INT))
),
totals AS (
  SELECT
    COALESCE((SELECT in_usd FROM inflow), 0) AS observed_in,
    COALESCE((SELECT out_usd FROM outflow), 0) AS observed_out,
    COALESCE((SELECT in_usd FROM inflow), 0) + COALESCE((SELECT out_usd FROM outflow), 0) AS observed_total,
    {declared} AS declared
)
SELECT
  CONCAT(CAST({window_days} AS STRING), '-day window') AS `Window`,
  observed_in   AS `Observed In (USD)`,
  observed_out  AS `Observed Out (USD)`,
  observed_total AS `Observed Total (USD)`,
  declared      AS `Declared (USD)`,
  CASE WHEN declared IS NULL THEN NULL ELSE observed_total - declared END AS `Delta (USD)`,
  CASE WHEN declared IS NULL OR declared = 0 THEN NULL
       ELSE ROUND(100.0 * (observed_total - declared) / declared, 1) END AS `Delta %`,
  CASE
    WHEN declared IS NULL THEN '📥 Awaiting Declared Volume USD input'
    WHEN observed_total = 0 AND declared > 0 THEN '⚠️ Declared but no on-chain volume observed in window'
    WHEN declared = 0 AND observed_total > 0 THEN '🚨 Observed but not declared'
    WHEN ABS(observed_total - declared) / NULLIF(declared, 0) <= 0.10 THEN '✅ Confirmed — within ±10%'
    WHEN ABS(observed_total - declared) / NULLIF(declared, 0) <= 0.25 THEN '🟡 Moderate variance — within ±25%'
    ELSE '🚨 Material variance — exceeds ±25%'
  END AS `Status`
FROM totals
"""


# ---------------------------------------------------------------------------
# Phase 3 — Behaviour
# ---------------------------------------------------------------------------

def sql_counterparty_mix(applicant: str) -> str:
    """P3.1 — Counterparty category mix, 90d, in+out combined."""
    return f"""
WITH in_cps AS (
  SELECT sender_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_category IS NOT NULL
  GROUP BY sender_category
),
out_cps AS (
  SELECT receiver_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_category IS NOT NULL
  GROUP BY receiver_category
)
SELECT category AS `Category`, SUM(usd) AS `USD (in + out, 90d)`
FROM (SELECT * FROM in_cps UNION ALL SELECT * FROM out_cps)
GROUP BY category
ORDER BY `USD (in + out, 90d)` DESC LIMIT 20
"""


# ---------------------------------------------------------------------------
# Phase 5 — Risk / Illicit exposure
# ---------------------------------------------------------------------------

def sql_illicit_exposure(applicant: str) -> str:
    """P5.1 — Severe/high category exposure, 90d, in+out combined, severity tier."""
    return f"""
WITH in_illicit AS (
  SELECT sender_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY sender_category
),
out_illicit AS (
  SELECT receiver_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY receiver_category
),
combined AS (
  SELECT category, SUM(usd) AS usd FROM (
    SELECT * FROM in_illicit UNION ALL SELECT * FROM out_illicit
  ) GROUP BY category
)
SELECT
  category AS `Category`,
  usd      AS `USD (in + out, 90d)`,
  CASE
    WHEN category IN ('sanctioned entity','sanctioned jurisdiction','special measures',
                      'ransomware','fraud shop','child abuse material',
                      'terrorist financing','stolen funds','seized funds') THEN '🛑 SEVERE'
    ELSE '⚠️ HIGH'
  END AS `Severity Tier`
FROM combined
WHERE usd > 0
ORDER BY usd DESC LIMIT 25
"""


# ---------------------------------------------------------------------------
# Phase 7 — Peer comparison
# ---------------------------------------------------------------------------

def sql_peer_comparison(applicant: str, peers: list[str]) -> str:
    """P7.1 — Applicant vs declared peer cohort, all-time metrics.

    Uses bidirectional substring match on each peer name so 'Kraken' picks up
    'Kraken.com', etc. Each peer becomes its own normalised row in output.
    """
    # Build a per-peer LIKE filter; use OR-chained match clauses
    peer_clauses = " OR ".join(name_match("entity_name", p) for p in peers if p)
    if not peer_clauses:
        peer_clauses = "1=0"
    return f"""
WITH universe AS (
  SELECT entity_name, received_usd, sent_usd, balance_usd, first, last
  FROM cross_chain.cluster_summary
  WHERE ({name_match("entity_name", applicant)})
     OR ({peer_clauses})
),
applicant_clusters AS (
  SELECT entity_name FROM universe WHERE {name_match("entity_name", applicant)}
),
metrics AS (
  SELECT entity_name,
    SUM(received_usd) AS total_received_usd,
    SUM(sent_usd)     AS total_sent_usd,
    SUM(balance_usd)  AS current_balance_usd,
    MAX(last)         AS last_activity,
    MIN(first)        AS first_activity
  FROM universe
  GROUP BY entity_name
)
SELECT
  CASE WHEN entity_name IN (SELECT entity_name FROM applicant_clusters)
       THEN concat('👉 ', entity_name) ELSE entity_name END AS `Firm`,
  CASE WHEN entity_name IN (SELECT entity_name FROM applicant_clusters)
       THEN 'APPLICANT' ELSE 'PEER' END AS `Role`,
  ROUND(total_received_usd, 0)  AS `Total Received USD (all-time)`,
  ROUND(current_balance_usd, 0) AS `Current Balance USD`,
  DATEDIFF(CURRENT_DATE(), last_activity)    AS `Days Since Last Activity`,
  DATEDIFF(last_activity, first_activity)    AS `Days on Chain`
FROM metrics
ORDER BY `Role` DESC, `Total Received USD (all-time)` DESC NULLS LAST
"""


# ---------------------------------------------------------------------------
# New analytics — wallet attribution, time series, monthly trend, cross-chain,
# Sankey flows
# ---------------------------------------------------------------------------

def sql_wallet_attribution(declared_wallets: list[str]) -> str:
    """P1.1 — For each declared wallet, show the cluster + entity it resolves to.

    The single most useful 'is this really their wallet?' check. Returns one
    row per declared address (LEFT JOINed so unattributed wallets still appear).
    """
    dw = lowered_address_values(declared_wallets)
    return f"""
WITH declared_wallets AS (SELECT address FROM {dw})
SELECT
  dw.address                                      AS `Declared Address`,
  COALESCE(c.entity_name, '— unattributed')       AS `Resolves To Entity`,
  COALESCE(c.entity_category, '—')                AS `Category`,
  COALESCE(ec.severity, 'clear')                  AS `Severity`,
  c.cluster_id                                    AS `Cluster ID`,
  c.chain_name                                    AS `Chain`,
  c.prior_entity_category                         AS `Prior Category`,
  c.entity_category_changed_at                    AS `Category Changed At`,
  CASE
    WHEN c.entity_name IS NULL                THEN '⚠️ Unattributed — applicant cannot prove control'
    WHEN ec.severity = 'severe'                THEN '🛑 SEVERE category — hard stop'
    WHEN ec.severity = 'high'                  THEN '⚠️ High-risk category — investigate'
    WHEN c.entity_category_changed_at IS NOT NULL THEN '🟡 Recategorised — review change'
    ELSE '✅ Attributed and clear'
  END                                             AS `Attribution Verdict`
FROM declared_wallets dw
LEFT JOIN cross_chain.clusters c ON c.address = dw.address
LEFT JOIN utils.entity_categories ec ON c.entity_category = ec.entity_category
ORDER BY
  CASE ec.severity WHEN 'severe' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
  dw.address
"""


def sql_volume_timeseries(applicant: str, window_days: int = 365) -> str:
    """P2.2 — Daily inflow + outflow over a window. Used for the trend chart."""
    return f"""
WITH inflow AS (
  SELECT date_day, SUM(amount_usd_total) AS in_usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(window_days)} AS INT))
  GROUP BY date_day
),
outflow AS (
  SELECT date_day, SUM(amount_usd_total) AS out_usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(window_days)} AS INT))
  GROUP BY date_day
)
SELECT
  COALESCE(i.date_day, o.date_day)         AS `Date`,
  COALESCE(i.in_usd, 0)                    AS `Inflow USD`,
  COALESCE(o.out_usd, 0)                   AS `Outflow USD`,
  COALESCE(i.in_usd, 0) + COALESCE(o.out_usd, 0) AS `Total USD`
FROM inflow i
FULL OUTER JOIN outflow o ON i.date_day = o.date_day
ORDER BY `Date`
"""


def sql_illicit_monthly_trend(applicant: str, months: int = 12) -> str:
    """P5.2 — Monthly illicit exposure trend over the last N months (in + out)."""
    return f"""
WITH base AS (
  SELECT DATE_TRUNC('month', date_day) AS month, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(months) * 31} AS INT))
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY DATE_TRUNC('month', date_day)
  UNION ALL
  SELECT DATE_TRUNC('month', date_day), SUM(amount_usd_total)
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(months) * 31} AS INT))
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY DATE_TRUNC('month', date_day)
)
SELECT month AS `Month`, SUM(usd) AS `Illicit Exposure USD`
FROM base
GROUP BY month
ORDER BY month
"""


def sql_cross_chain_breakdown(applicant: str, window_days: int = 90) -> str:
    """Multi-chain mix — shows which blockchains the applicant operates on."""
    return f"""
WITH in_by_chain AS (
  SELECT chain_name, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(window_days)} AS INT))
    AND chain_name IS NOT NULL
  GROUP BY chain_name
),
out_by_chain AS (
  SELECT chain_name, SUM(amount_usd_total) AS usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), CAST({int(window_days)} AS INT))
    AND chain_name IS NOT NULL
  GROUP BY chain_name
)
SELECT
  chain_name AS `Chain`,
  SUM(usd)   AS `USD (in + out, {int(window_days)}d)`
FROM (SELECT * FROM in_by_chain UNION ALL SELECT * FROM out_by_chain)
GROUP BY chain_name
ORDER BY `USD (in + out, {int(window_days)}d)` DESC
"""


def sql_counterparty_flows_sankey(applicant: str, top_n: int = 15) -> str:
    """P3.2 — Sankey-ready source/target/value rows for in+out flows by category."""
    return f"""
WITH inflow AS (
  SELECT sender_category AS source, {q(applicant)} AS target,
         SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND sender_category IS NOT NULL
  GROUP BY sender_category
),
outflow AS (
  SELECT {q(applicant)} AS source, receiver_category AS target,
         SUM(amount_usd_total) AS usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND receiver_category IS NOT NULL
  GROUP BY receiver_category
)
SELECT source AS `Source`, target AS `Target`, usd AS `USD`
FROM (SELECT * FROM inflow UNION ALL SELECT * FROM outflow)
WHERE usd > 0
ORDER BY usd DESC LIMIT {int(top_n) * 2}
"""


# ===========================================================================
# Batch 2 — Tier 1 + Tier 2 investigative tiles
# ===========================================================================

# --- TOP 4 ---

def sql_top_counterparties(applicant: str, limit: int = 25) -> str:
    """P3.3 — Top N named counterparties by bilateral volume, 90d, with risk flag."""
    return f"""
WITH inflow AS (
  SELECT sender_name AS counterparty, sender_category AS category, SUM(amount_usd_total) AS usd_in
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND sender_name IS NOT NULL
    AND NOT ({name_match("sender_name", applicant)})
  GROUP BY sender_name, sender_category
),
outflow AS (
  SELECT receiver_name AS counterparty, receiver_category AS category, SUM(amount_usd_total) AS usd_out
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND receiver_name IS NOT NULL
    AND NOT ({name_match("receiver_name", applicant)})
  GROUP BY receiver_name, receiver_category
)
SELECT
  counterparty AS `Counterparty`, category AS `Category`,
  ROUND(SUM(usd_in), 0)  AS `USD In`,
  ROUND(SUM(usd_out), 0) AS `USD Out`,
  ROUND(SUM(usd_in + usd_out), 0) AS `Total Bilateral USD`,
  CASE
    WHEN category IN ('sanctioned entity', 'sanctioned jurisdiction', 'special measures',
                      'ransomware', 'fraud shop', 'child abuse material',
                      'terrorist financing', 'stolen funds', 'seized funds') THEN '🛑 SEVERE'
    WHEN category IN ('darknet market', 'scam', 'mixing', 'no kyc exchange',
                      'high risk exchange', 'high risk jurisdiction') THEN '⚠️ HIGH'
    WHEN category IN ('exchange', 'institutional platform', 'merchant services') THEN '✅ Regulated counterparty'
    ELSE '— other'
  END AS `Risk Flag`
FROM (
  SELECT counterparty, category, usd_in, 0.0 AS usd_out FROM inflow
  UNION ALL
  SELECT counterparty, category, 0.0 AS usd_in, usd_out FROM outflow
)
GROUP BY counterparty, category
ORDER BY `Total Bilateral USD` DESC LIMIT {int(limit)}
"""


def sql_top_illicit_counterparties(applicant: str, limit: int = 25) -> str:
    """P5.4 — Top N named counterparties limited to high/severe categories, 90d."""
    return f"""
WITH in_cps AS (
  SELECT sender_name AS counterparty, sender_category AS category, SUM(amount_usd_total) AS usd_in
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_name IS NOT NULL
    AND NOT ({name_match("sender_name", applicant)})
    AND sender_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY sender_name, sender_category
),
out_cps AS (
  SELECT receiver_name AS counterparty, receiver_category AS category, SUM(amount_usd_total) AS usd_out
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_name IS NOT NULL
    AND NOT ({name_match("receiver_name", applicant)})
    AND receiver_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY receiver_name, receiver_category
)
SELECT
  counterparty AS `Counterparty`,
  category     AS `Category`,
  ROUND(SUM(usd_in), 0) AS `USD In`,
  ROUND(SUM(usd_out), 0) AS `USD Out`,
  ROUND(SUM(usd_in + usd_out), 0) AS `Total USD`,
  CASE
    WHEN category IN ('sanctioned entity','sanctioned jurisdiction','special measures',
                      'ransomware','fraud shop','child abuse material',
                      'terrorist financing','stolen funds','seized funds') THEN '🛑 SEVERE'
    ELSE '⚠️ HIGH'
  END AS `Severity Tier`
FROM (
  SELECT counterparty, category, usd_in, 0.0 AS usd_out FROM in_cps
  UNION ALL
  SELECT counterparty, category, 0.0 AS usd_in, usd_out FROM out_cps
)
GROUP BY counterparty, category
ORDER BY `Total USD` DESC LIMIT {int(limit)}
"""


def sql_declared_vs_observed_geo(applicant: str, declared_territories: str) -> str:
    """P1.4 — Wallet Geo Signals: which countries' clusters send to the applicant,
    and were they on the applicant's declared territories list?"""
    # Parse declared list once in Python (cleaner than relying on Spark's split)
    declared = [t.strip().upper() for t in (declared_territories or "").split(",") if t.strip()]
    if declared:
        declared_vals = values_list(declared, col="country_code")
        declared_cte = f"SELECT country_code FROM {declared_vals}"
    else:
        declared_cte = "SELECT CAST(NULL AS STRING) AS country_code WHERE 1=0"
    return f"""
WITH declared AS ({declared_cte}),
applicant_inflows AS (
  SELECT DISTINCT sender_cluster_id AS cluster_id, chain_id
  FROM cross_chain.transfers_clustered
  WHERE {name_match("receiver_name", applicant)}
    AND transaction_timestamp >= DATE_SUB(CURRENT_DATE(), 30)
    AND sender_name IS NULL
    AND sender_cluster_id IS NOT NULL
),
geo AS (
  SELECT ai.cluster_id, wgs.country_code, wgs.confidence_level
  FROM applicant_inflows ai
  LEFT JOIN cross_chain.behavioral_wallet_geo_signals wgs
    ON wgs.cluster_id = ai.cluster_id AND wgs.chain_id = ai.chain_id
),
by_country AS (
  SELECT country_code,
    COUNT(DISTINCT cluster_id) AS clusters,
    COUNT(DISTINCT CASE WHEN confidence_level IN ('Very likely', 'Almost certain') THEN cluster_id END) AS high_conf
  FROM geo WHERE country_code IS NOT NULL
  GROUP BY country_code
)
SELECT
  bc.country_code AS `Country`,
  CASE WHEN d.country_code IS NOT NULL THEN '✅ Declared' ELSE '🚨 Not declared' END AS `Declared?`,
  bc.clusters AS `Counterparty Clusters (30d)`,
  bc.high_conf AS `High-Confidence (Very Likely+)`
FROM by_country bc
LEFT JOIN declared d ON bc.country_code = d.country_code
ORDER BY `Counterparty Clusters (30d)` DESC LIMIT 25
"""


def sql_self_hosted_profile(applicant: str) -> str:
    """P4.3 — Inflow + outflow split by named vs unhosted counterparty, 90d."""
    return f"""
WITH inflow AS (
  SELECT
    SUM(CASE WHEN sender_name IS NOT NULL THEN amount_usd_total ELSE 0 END) AS named_usd,
    SUM(CASE WHEN sender_name IS NULL     THEN amount_usd_total ELSE 0 END) AS unhosted_usd,
    SUM(amount_usd_total) AS total_usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
),
outflow AS (
  SELECT
    SUM(CASE WHEN receiver_name IS NOT NULL THEN amount_usd_total ELSE 0 END) AS named_usd,
    SUM(CASE WHEN receiver_name IS NULL     THEN amount_usd_total ELSE 0 END) AS unhosted_usd,
    SUM(amount_usd_total) AS total_usd
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
)
SELECT
  'Inflow' AS `Direction`,
  ROUND((SELECT total_usd FROM inflow), 0)    AS `Total USD (90d)`,
  ROUND((SELECT named_usd FROM inflow), 0)    AS `From Named Entities`,
  ROUND((SELECT unhosted_usd FROM inflow), 0) AS `From Unhosted Wallets`,
  ROUND(100.0 * (SELECT unhosted_usd FROM inflow) / NULLIF((SELECT total_usd FROM inflow), 0), 1)
    AS `Unhosted %`,
  CASE
    WHEN 100.0 * (SELECT unhosted_usd FROM inflow) / NULLIF((SELECT total_usd FROM inflow), 0) > 70
      THEN '⚠️ High unhosted % — heavy direct retail or self-custody-friendly'
    WHEN 100.0 * (SELECT unhosted_usd FROM inflow) / NULLIF((SELECT total_usd FROM inflow), 0) < 20
      THEN '✅ Predominantly named-entity flows — institutional / B2B pattern'
    ELSE '🟡 Mixed — typical retail/institutional VASP shape'
  END AS `Self-Hosted Profile`
UNION ALL
SELECT
  'Outflow',
  ROUND((SELECT total_usd FROM outflow), 0),
  ROUND((SELECT named_usd FROM outflow), 0),
  ROUND((SELECT unhosted_usd FROM outflow), 0),
  ROUND(100.0 * (SELECT unhosted_usd FROM outflow) / NULLIF((SELECT total_usd FROM outflow), 0), 1),
  CASE
    WHEN 100.0 * (SELECT unhosted_usd FROM outflow) / NULLIF((SELECT total_usd FROM outflow), 0) > 70
      THEN '⚠️ High unhosted % — heavy direct retail or self-custody-friendly'
    WHEN 100.0 * (SELECT unhosted_usd FROM outflow) / NULLIF((SELECT total_usd FROM outflow), 0) < 20
      THEN '✅ Predominantly named-entity flows — institutional / B2B pattern'
    ELSE '🟡 Mixed — typical retail/institutional VASP shape'
  END
"""


# --- TIER 2 ---

def sql_adverse_velocity(applicant: str) -> str:
    """P5.6 — Adverse-counterparty velocity: this 90d vs prior 90d, in+out."""
    return f"""
WITH cur_q AS (
  SELECT sender_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY sender_category
  UNION ALL
  SELECT receiver_category, SUM(amount_usd_total)
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY receiver_category
),
prev_q AS (
  SELECT sender_category AS category, SUM(amount_usd_total) AS usd
  FROM cross_chain.receiving_exposure_aggregation_daily
  WHERE {name_match("receiver_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 180)
    AND date_day <  DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND sender_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY sender_category
  UNION ALL
  SELECT receiver_category, SUM(amount_usd_total)
  FROM cross_chain.sending_exposure_aggregation_daily
  WHERE {name_match("sender_name", applicant)}
    AND date_day >= DATE_SUB(CURRENT_DATE(), 180)
    AND date_day <  DATE_SUB(CURRENT_DATE(), 90)
    AND asset_id IN (SELECT asset_id FROM utils.assets)
    AND receiver_category IN (SELECT entity_category FROM utils.entity_categories WHERE severity IN ('high','severe'))
  GROUP BY receiver_category
),
cur_agg AS (SELECT category, SUM(usd) AS usd FROM cur_q  GROUP BY category),
prev_agg AS (SELECT category, SUM(usd) AS usd FROM prev_q GROUP BY category)
SELECT
  COALESCE(c.category, p.category) AS `Category`,
  ROUND(COALESCE(p.usd, 0), 0) AS `Prev 90d USD`,
  ROUND(COALESCE(c.usd, 0), 0) AS `Curr 90d USD`,
  ROUND(COALESCE(c.usd, 0) - COALESCE(p.usd, 0), 0) AS `Delta USD`,
  CASE WHEN COALESCE(p.usd, 0) = 0 THEN NULL
       ELSE ROUND(100.0 * (COALESCE(c.usd, 0) - COALESCE(p.usd, 0)) / p.usd, 1) END
    AS `Delta %`,
  CASE
    WHEN COALESCE(p.usd, 0) = 0 AND COALESCE(c.usd, 0) > 1000 THEN '🚨 New exposure this quarter (was zero)'
    WHEN COALESCE(c.usd, 0) = 0 AND COALESCE(p.usd, 0) > 1000 THEN '✅ Exposure ended this quarter'
    WHEN COALESCE(p.usd, 0) = 0 THEN '— immaterial both quarters'
    WHEN COALESCE(c.usd, 0) > 2.0  * p.usd THEN '🚨 Accelerating (>2x prior quarter)'
    WHEN COALESCE(c.usd, 0) > 1.25 * p.usd THEN '⚠️ Increasing (>25%)'
    WHEN COALESCE(c.usd, 0) < 0.5  * p.usd THEN '🟢 Decelerating (<50% of prior)'
    ELSE '— stable (within ±25%)'
  END AS `Velocity Verdict`
FROM cur_agg c
FULL OUTER JOIN prev_agg p ON c.category = p.category
WHERE COALESCE(c.usd, 0) + COALESCE(p.usd, 0) > 0
ORDER BY ABS(COALESCE(c.usd, 0) - COALESCE(p.usd, 0)) DESC LIMIT 25
"""


def sql_cluster_lineage(applicant: str) -> str:
    """P1.3 — Category-change events: catches re-categorisations from sanctioned->X
    or X->sanctioned. Sparse dataset (Chainalysis populates this mainly for
    sanctioned-entity reclassifications)."""
    return f"""
WITH lineage AS (
  SELECT entity_category, prior_entity_category, entity_category_changed_at, chain_name,
         COUNT(DISTINCT address) AS addresses_affected
  FROM cross_chain.clusters
  WHERE {name_match("entity_name", applicant)}
    AND entity_category_changed_at IS NOT NULL
  GROUP BY entity_category, prior_entity_category, entity_category_changed_at, chain_name
)
SELECT
  entity_category_changed_at AS `Changed At`,
  prior_entity_category      AS `Previous Category`,
  entity_category            AS `New Category`,
  chain_name                 AS `Chain`,
  addresses_affected         AS `Addresses Affected`,
  CASE
    WHEN entity_category IN ('sanctioned entity', 'sanctioned jurisdiction', 'special measures')
      THEN '🛑 Reclassified to sanctioned/special-measures status'
    WHEN prior_entity_category IN ('sanctioned entity', 'sanctioned jurisdiction', 'special measures')
      THEN '✅ De-listed from sanctioned status'
    ELSE '📝 Category change recorded'
  END AS `Lineage Event`
FROM lineage
ORDER BY `Changed At` DESC NULLS LAST
"""


def sql_affiliate_reconciliation(applicant: str, declared_affiliates: list[str]) -> str:
    """C7 — Bilateral on-chain flow between applicant and each *declared* affiliate.
    Tests the 'we have no group structure' claim — observed bilateral flow with an
    undeclared sister entity would surface in P3.3 instead. Empty input -> info row.
    """
    affiliates = [a.strip() for a in declared_affiliates if a and a.strip()]
    if not affiliates:
        return """
SELECT
  '📥 No declared affiliated firms in intake' AS `Status`,
  'Add comma-separated firm names to the Declared affiliated firms intake field' AS `Action`,
  CAST(0 AS DOUBLE) AS `Bilateral USD (90d)`
FROM (SELECT 1 AS x) t
"""
    # Build a UNION of per-affiliate flow checks
    parts = []
    for aff in affiliates:
        parts.append(f"""
SELECT
  {q(aff)} AS `Declared Affiliate`,
  COALESCE((
    SELECT SUM(amount_usd_total)
    FROM cross_chain.receiving_exposure_aggregation_daily
    WHERE {name_match("receiver_name", applicant)}
      AND {name_match("sender_name", aff)}
      AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
  ), 0) AS `Inflow From Affiliate (90d USD)`,
  COALESCE((
    SELECT SUM(amount_usd_total)
    FROM cross_chain.sending_exposure_aggregation_daily
    WHERE {name_match("sender_name", applicant)}
      AND {name_match("receiver_name", aff)}
      AND date_day >= DATE_SUB(CURRENT_DATE(), 90)
  ), 0) AS `Outflow To Affiliate (90d USD)`
""")
    union = " UNION ALL ".join(parts)
    return f"""
WITH bilateral AS (
  {union}
)
SELECT
  `Declared Affiliate`,
  ROUND(`Inflow From Affiliate (90d USD)`, 0)  AS `Inflow USD (90d)`,
  ROUND(`Outflow To Affiliate (90d USD)`, 0)   AS `Outflow USD (90d)`,
  ROUND(`Inflow From Affiliate (90d USD)` + `Outflow To Affiliate (90d USD)`, 0)
    AS `Total Bilateral USD (90d)`,
  CASE
    WHEN `Inflow From Affiliate (90d USD)` + `Outflow To Affiliate (90d USD)` = 0
      THEN '— No observed bilateral flow (declared but inactive on-chain, or operates via off-chain rails)'
    WHEN `Inflow From Affiliate (90d USD)` + `Outflow To Affiliate (90d USD)` >= 1000000
      THEN '✅ Confirmed material bilateral flow — affiliation visible on-chain'
    ELSE '🟡 Small bilateral flow recorded'
  END AS `Reconciliation Status`
FROM bilateral
ORDER BY `Total Bilateral USD (90d)` DESC
"""


def sql_internal_consistency(applicant: str, declared_business_model: str) -> str:
    """P2.5 — Tx-size distribution vs declared business model (Retail / Institutional /
    OTC / Mixed). Substring-matches declared_business_model since the intake is free
    text (not a fixed dropdown in this app)."""
    bm = (declared_business_model or "").strip()
    bm_lower = bm.lower()
    # Pick a hint based on substring presence
    if any(k in bm_lower for k in ("otc",)):
        kind = "OTC"
    elif any(k in bm_lower for k in ("institutional", "wholesale", "b2b")):
        kind = "Institutional"
    elif any(k in bm_lower for k in ("retail", "consumer")):
        kind = "Retail"
    elif any(k in bm_lower for k in ("mixed", "centralised exchange", "exchange")):
        kind = "Mixed"
    else:
        kind = ""
    return f"""
WITH tx_sizes AS (
  SELECT
    CASE
      WHEN amount_usd < 100     THEN 'retail_micro'
      WHEN amount_usd < 1000    THEN 'retail_small'
      WHEN amount_usd < 10000   THEN 'retail_large'
      WHEN amount_usd < 100000  THEN 'institutional_small'
      WHEN amount_usd < 1000000 THEN 'institutional_large'
      ELSE 'institutional_xlarge'
    END AS bucket,
    amount_usd
  FROM cross_chain.transfers_clustered
  WHERE {name_match("receiver_name", applicant)}
    AND transaction_timestamp >= DATE_SUB(CURRENT_DATE(), 30)
    AND amount_usd > 0
),
shape AS (
  SELECT
    COUNT(*) AS total_txs,
    SUM(CASE WHEN bucket IN ('retail_micro', 'retail_small', 'retail_large') THEN 1 ELSE 0 END)              AS retail_txs,
    SUM(CASE WHEN bucket IN ('institutional_small', 'institutional_large', 'institutional_xlarge') THEN 1 ELSE 0 END) AS institutional_txs
  FROM tx_sizes
)
SELECT
  {q(bm) if bm else "'(none declared)'"} AS `Declared Business Model`,
  {q(kind) if kind else "'(unclassified)'"}   AS `Inferred Type`,
  total_txs                              AS `Total Transactions (30d)`,
  ROUND(100.0 * retail_txs        / NULLIF(total_txs, 0), 1) AS `Retail-size %`,
  ROUND(100.0 * institutional_txs / NULLIF(total_txs, 0), 1) AS `Institutional-size %`,
  CASE
    WHEN total_txs = 0 THEN '⚠️ No transactions in 30-day window'
    WHEN {q(kind)} = '' THEN '📥 Couldn''t infer model from declared text — verdict pending'
    WHEN {q(kind)} = 'Institutional' AND 100.0 * retail_txs / NULLIF(total_txs, 0) > 30
      THEN '🚨 Declared institutional but >30% retail-sized transfers'
    WHEN {q(kind)} = 'Retail' AND 100.0 * institutional_txs / NULLIF(total_txs, 0) > 30
      THEN '🚨 Declared retail but >30% institutional-sized transfers'
    WHEN {q(kind)} = 'OTC' AND 100.0 * retail_txs / NULLIF(total_txs, 0) > 10
      THEN '🚨 Declared OTC but >10% retail-sized transfers'
    WHEN {q(kind)} = 'Mixed' THEN '✅ Mixed model — distribution consistent by definition'
    ELSE '✅ Consistent with declared business model'
  END AS `Consistency Verdict`
FROM shape
"""
