"""
SQL query functions for the UK FCA Firm Authorisation Workbench.

Every function takes the applicant name (str) as its first argument,
builds a Data Solutions SQL query, and returns a cached DataFrame.

Table references follow Chainalysis Data Solutions naming conventions
(Databricks SQL dialect, backtick aliases, schema.table format).
"""

import pandas as pd
from utils.data import ds_query_cached, esc


# ── Phase 0 ────────────────────────────────────────────────────────────

def sql_perimeter_check(name: str) -> pd.DataFrame:
    """Check whether the applicant has an on-chain footprint in DS."""
    sql = f"""
    SELECT entity_name,
           entity_category,
           chain_name,
           total_received_usd  AS `total_received_usd`,
           total_sent_usd      AS `total_sent_usd`
    FROM cross_chain.cluster_summary
    WHERE entity_name ILIKE '%{esc(name)}%'
    ORDER BY total_received_usd DESC
    LIMIT 20
    """
    return ds_query_cached(sql)


def sql_sanctions_screen(wallets: list[str]) -> pd.DataFrame:
    """Screen a list of wallet addresses against sanctioned-entity labels."""
    if not wallets:
        return pd.DataFrame()
    addr_list = ", ".join(f"'{esc(w)}'" for w in wallets)
    sql = f"""
    SELECT address,
           entity_name    AS `entity_name`,
           entity_category AS `entity_category`,
           label
    FROM cross_chain.address_level_identifications
    WHERE address IN ({addr_list})
      AND entity_category IN ('sanctioned entity')
    LIMIT 100
    """
    return ds_query_cached(sql)


def sql_risk_tier(name: str) -> pd.DataFrame:
    """Return risk-tier summary for the applicant's clusters."""
    sql = f"""
    SELECT entity_name,
           entity_category,
           chain_name,
           SUM(total_received_usd) AS `total_received_usd`,
           SUM(total_sent_usd)     AS `total_sent_usd`
    FROM cross_chain.cluster_summary
    WHERE entity_name ILIKE '%{esc(name)}%'
    GROUP BY entity_name, entity_category, chain_name
    ORDER BY `total_received_usd` DESC
    LIMIT 10
    """
    return ds_query_cached(sql)


# ── Phase 1 ────────────────────────────────────────────────────────────

def sql_time_on_chain(name: str) -> pd.DataFrame:
    """Earliest and latest on-chain activity per chain for the applicant."""
    sql = f"""
    SELECT entity_name,
           chain_name,
           MIN(first_transaction_timestamp) AS `first_seen`,
           MAX(last_transaction_timestamp)  AS `last_seen`
    FROM cross_chain.cluster_summary
    WHERE entity_name ILIKE '%{esc(name)}%'
    GROUP BY entity_name, chain_name
    ORDER BY `first_seen`
    LIMIT 20
    """
    return ds_query_cached(sql)


def sql_osint(name: str) -> pd.DataFrame:
    """Return address-level identifications (OSINT scan) for the applicant."""
    sql = f"""
    SELECT address,
           label,
           text          AS `detail`,
           entity_name   AS `parent_cluster`
    FROM cross_chain.address_level_identifications
    WHERE entity_name ILIKE '%{esc(name)}%'
       OR label       ILIKE '%{esc(name)}%'
    LIMIT 50
    """
    return ds_query_cached(sql)


# ── Phase 2 ────────────────────────────────────────────────────────────

def sql_volume_reconciliation(name: str) -> pd.DataFrame:
    """Aggregate observed volumes per chain & asset for reconciliation."""
    sql = f"""
    SELECT entity_name,
           chain_name,
           asset_symbol,
           SUM(total_received_usd) AS `total_received_usd`,
           SUM(total_sent_usd)     AS `total_sent_usd`,
           SUM(balance_usd)        AS `balance_usd`
    FROM cross_chain.cluster_summary
    WHERE entity_name ILIKE '%{esc(name)}%'
    GROUP BY entity_name, chain_name, asset_symbol
    ORDER BY `total_received_usd` DESC
    LIMIT 50
    """
    return ds_query_cached(sql)


# ── Phase 3 ────────────────────────────────────────────────────────────

def sql_counterparty_mix(name: str) -> pd.DataFrame:
    """Counterparty-category breakdown (for pie chart)."""
    sql = f"""
    SELECT receiver_category           AS `counterparty_category`,
           COUNT(*)                    AS `transfer_count`,
           SUM(total_amount_usd)       AS `total_usd`
    FROM cross_chain.sending_exposure_aggregation_alltime
    WHERE sender_name ILIKE '%{esc(name)}%'
      AND receiver_category IS NOT NULL
    GROUP BY receiver_category
    ORDER BY `total_usd` DESC
    LIMIT 20
    """
    return ds_query_cached(sql)


# ── Phase 5 ────────────────────────────────────────────────────────────

_ILLICIT_CATEGORIES = (
    "'darknet market'",
    "'ransomware'",
    "'stolen funds'",
    "'fraud shop'",
    "'sanctioned entity'",
    "'child exploitation'",
    "'terrorist financing'",
    "'drug vendor'",
    "'scam'",
    "'mixing'",
)


def sql_illicit_exposure(name: str) -> pd.DataFrame:
    """Illicit-category exposure for the applicant."""
    cats = ", ".join(_ILLICIT_CATEGORIES)
    sql = f"""
    SELECT receiver_category           AS `category`,
           receiver_name               AS `counterparty`,
           SUM(total_amount_usd)       AS `exposure_usd`
    FROM cross_chain.sending_exposure_aggregation_alltime
    WHERE sender_name ILIKE '%{esc(name)}%'
      AND receiver_category IN ({cats})
    GROUP BY receiver_category, receiver_name
    ORDER BY `exposure_usd` DESC
    LIMIT 50
    """
    return ds_query_cached(sql)


# ── Phase 7 ────────────────────────────────────────────────────────────

def sql_peer_comparison(name: str) -> pd.DataFrame:
    """Compare the applicant against peers in the same entity category."""
    sql = f"""
    SELECT entity_name,
           entity_category,
           SUM(total_received_usd) AS `total_received_usd`,
           SUM(total_sent_usd)     AS `total_sent_usd`
    FROM cross_chain.cluster_summary
    WHERE entity_category = (
        SELECT entity_category
        FROM cross_chain.cluster_summary
        WHERE entity_name ILIKE '%{esc(name)}%'
        LIMIT 1
    )
    GROUP BY entity_name, entity_category
    ORDER BY `total_received_usd` DESC
    LIMIT 20
    """
    return ds_query_cached(sql)
