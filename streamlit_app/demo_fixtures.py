"""Snapshot fixtures for the three pre-loaded demo cases.

These are *plausible* query results — not captured from live DS runs. They
exist so a recorded walkthrough doesn't have to wait 60-180 seconds for each
async query to complete on camera.

To replace with real captured data later: run each query in normal mode for
the chosen applicant, copy the persisted ``_results`` block out of the
SQLite ``cases.state_json`` column, paste it as a Python dict below.

Structure: ``DEMO_FIXTURES[demo_key][phase_name][result_key] = {records, columns, label, ran_at}``
That matches the shape ``save_result()`` writes to ``state[phaseN]['_results']``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Pin all "ran_at" timestamps to the same recent moment so the demo looks
# coherent on screen (no "last run 3 days ago" mixed with "just now").
_NOW = datetime.now(timezone.utc).isoformat()


def _r(records: list[dict], label: str) -> dict:
    """Helper: build a saved-result dict in the shape save_result() uses."""
    cols = list(records[0].keys()) if records else []
    return {
        "label": label,
        "records": records,
        "columns": cols,
        "ran_at": _NOW,
    }


# ---------------------------------------------------------------------------
# 🟢 Coinbase — clean licensed case
# ---------------------------------------------------------------------------

COINBASE = {
    "phase0": {
        "perimeter": _r([{
            "Perimeter Status": "✅ On FCA register",
            "Register Status": "licensed",
            "UK Confidence": "Very likely",
        }], "Perimeter check"),
        "sanctions": _r([
            {"Declared Address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
             "Entity (if attributed)": "Coinbase.com", "Category": "exchange",
             "Severity": "clear", "Prior Category": None, "Category Changed At": None,
             "Chain": "ethereum", "Screen Result": "✅ Clear"},
            {"Declared Address": "0x503828976d22510aad0201ac7ec88293211d23da",
             "Entity (if attributed)": "Coinbase.com", "Category": "exchange",
             "Severity": "clear", "Prior Category": None, "Category Changed At": None,
             "Chain": "ethereum", "Screen Result": "✅ Clear"},
        ], "Sanctions screen"),
        "risk_tier": _r([{
            "Risk Tier": "🟠 Intensive (size trigger)",
            "Total Received USD": 1.42e11,
            "FCA Register Status": "licensed",
            "UK Confidence": "Very likely",
        }], "Risk tier"),
        "affiliates": _r([
            {"Declared Affiliate": "Coinbase Inc",
             "Inflow USD (90d)": 4_280_000_000, "Outflow USD (90d)": 3_950_000_000,
             "Total Bilateral USD (90d)": 8_230_000_000,
             "Reconciliation Status": "✅ Confirmed material bilateral flow — affiliation visible on-chain"},
            {"Declared Affiliate": "Coinbase Custody",
             "Inflow USD (90d)": 1_120_000_000, "Outflow USD (90d)": 880_000_000,
             "Total Bilateral USD (90d)": 2_000_000_000,
             "Reconciliation Status": "✅ Confirmed material bilateral flow — affiliation visible on-chain"},
        ], "Affiliate reconciliation"),
    },
    "phase1": {
        "wallet_attribution": _r([
            {"Declared Address": "0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
             "Resolves To Entity": "Coinbase.com", "Category": "exchange",
             "Severity": "clear", "Cluster ID": "btc_cluster_1042",
             "Chain": "ethereum", "Prior Category": None, "Category Changed At": None,
             "Attribution Verdict": "✅ Attributed and clear"},
            {"Declared Address": "0x503828976d22510aad0201ac7ec88293211d23da",
             "Resolves To Entity": "Coinbase.com", "Category": "exchange",
             "Severity": "clear", "Cluster ID": "btc_cluster_1042",
             "Chain": "ethereum", "Prior Category": None, "Category Changed At": None,
             "Attribution Verdict": "✅ Attributed and clear"},
        ], "Wallet attribution"),
        "time_on_chain": _r([{
            "First Observed": "2012-06-20",
            "Last Observed": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "Days On Chain": 5089,
            "Days Since Last Active": 1,
            "Maturity Signal": "🟢 5+ years on chain — established",
        }], "Time on chain"),
        "cluster_lineage": _r([], "Cluster lineage"),  # empty — Coinbase has no reclassifications
        "geo_comparison": _r([
            {"Country": "GB", "Declared?": "✅ Declared",
             "Counterparty Clusters (30d)": 18_420, "High-Confidence (Very Likely+)": 11_840},
            {"Country": "US", "Declared?": "🚨 Not declared",
             "Counterparty Clusters (30d)": 14_280, "High-Confidence (Very Likely+)": 9_120},
            {"Country": "DE", "Declared?": "🚨 Not declared",
             "Counterparty Clusters (30d)": 6_540, "High-Confidence (Very Likely+)": 4_210},
            {"Country": "IE", "Declared?": "✅ Declared",
             "Counterparty Clusters (30d)": 3_820, "High-Confidence (Very Likely+)": 2_680},
            {"Country": "FR", "Declared?": "🚨 Not declared",
             "Counterparty Clusters (30d)": 2_910, "High-Confidence (Very Likely+)": 1_840},
            {"Country": "NL", "Declared?": "🚨 Not declared",
             "Counterparty Clusters (30d)": 1_640, "High-Confidence (Very Likely+)": 1_120},
            {"Country": "ES", "Declared?": "🚨 Not declared",
             "Counterparty Clusters (30d)": 1_320, "High-Confidence (Very Likely+)": 890},
        ], "Declared vs observed geo"),
        "osint_summary": _r([
            {"OSINT Source": "blockchain.info", "Findings": 1842,
             "Earliest": "2013-04-12", "Latest": "2024-08-09",
             "Source Quality": "🟢 High-quality attribution source"},
            {"OSINT Source": "shapeshift.io", "Findings": 612,
             "Earliest": "2015-02-08", "Latest": "2023-11-14",
             "Source Quality": "🟢 High-quality attribution source"},
            {"OSINT Source": "bitcoin_abuse", "Findings": 47,
             "Earliest": "2019-06-22", "Latest": "2024-07-30",
             "Source Quality": "⚠️ Adverse-signal source"},
            {"OSINT Source": "bitcointalk.org", "Findings": 312,
             "Earliest": "2013-09-14", "Latest": "2024-09-01",
             "Source Quality": "🟡 Social-media source (low confidence)"},
        ], "OSINT summary"),
    },
    "phase2": {
        "volume": _r([{
            "Window": "90-day window",
            "Observed In (USD)": 27_840_000_000,
            "Observed Out (USD)": 24_120_000_000,
            "Observed Total (USD)": 51_960_000_000,
            "Declared (USD)": 50_000_000_000,
            "Delta (USD)": 1_960_000_000,
            "Delta %": 3.9,
            "Status": "✅ Confirmed — within ±10%",
        }], "Volume reconciliation"),
        "timeseries": _r(
            [
                {"Date": (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d"),
                 "Inflow USD": 280_000_000 + (d % 7) * 30_000_000 + (d % 30) * 5_000_000,
                 "Outflow USD": 240_000_000 + (d % 7) * 25_000_000 + (d % 30) * 4_500_000,
                 "Total USD": 520_000_000 + (d % 7) * 55_000_000 + (d % 30) * 9_500_000}
                for d in range(365, 0, -1)
            ],
            "Volume time series",
        ),
        "cross_chain": _r([
            {"Chain": "ethereum",  "USD (in + out, 90d)": 28_420_000_000},
            {"Chain": "bitcoin",   "USD (in + out, 90d)": 14_120_000_000},
            {"Chain": "solana",    "USD (in + out, 90d)":  4_840_000_000},
            {"Chain": "polygon",   "USD (in + out, 90d)":  2_140_000_000},
            {"Chain": "arbitrum",  "USD (in + out, 90d)":  1_820_000_000},
            {"Chain": "base",      "USD (in + out, 90d)":    420_000_000},
            {"Chain": "optimism",  "USD (in + out, 90d)":    198_000_000},
        ], "Cross-chain breakdown"),
        "consistency": _r([{
            "Declared Business Model": "Centralised exchange and custody",
            "Inferred Type": "Mixed",
            "Total Transactions (30d)": 8_412_330,
            "Retail-size %": 62.4,
            "Institutional-size %": 37.6,
            "Consistency Verdict": "✅ Mixed model — distribution consistent by definition",
        }], "Internal consistency"),
    },
    "phase3": {
        "counterparty_mix": _r([
            {"Category": "exchange",                "USD (in + out, 90d)": 18_240_000_000},
            {"Category": "institutional platform",  "USD (in + out, 90d)":  9_120_000_000},
            {"Category": "merchant services",       "USD (in + out, 90d)":  6_840_000_000},
            {"Category": "mining",                  "USD (in + out, 90d)":  4_210_000_000},
            {"Category": "atm",                     "USD (in + out, 90d)":  2_180_000_000},
            {"Category": "high risk exchange",      "USD (in + out, 90d)":  1_240_000_000},
            {"Category": "gambling",                "USD (in + out, 90d)":    820_000_000},
            {"Category": "darknet market",          "USD (in + out, 90d)":     12_400_000},
            {"Category": "scam",                    "USD (in + out, 90d)":      8_240_000},
            {"Category": "sanctioned entity",       "USD (in + out, 90d)":      2_180_000},
        ], "Counterparty mix"),
        "sankey": _r([
            {"Source": "exchange",                "Target": "Coinbase.com",         "USD": 10_240_000_000},
            {"Source": "institutional platform",  "Target": "Coinbase.com",         "USD":  5_120_000_000},
            {"Source": "merchant services",       "Target": "Coinbase.com",         "USD":  3_420_000_000},
            {"Source": "mining",                  "Target": "Coinbase.com",         "USD":  2_180_000_000},
            {"Source": "atm",                     "Target": "Coinbase.com",         "USD":  1_240_000_000},
            {"Source": "Coinbase.com",            "Target": "exchange",             "USD":  8_000_000_000},
            {"Source": "Coinbase.com",            "Target": "merchant services",    "USD":  3_420_000_000},
            {"Source": "Coinbase.com",            "Target": "institutional platform","USD": 4_000_000_000},
            {"Source": "Coinbase.com",            "Target": "mining",               "USD":  2_030_000_000},
            {"Source": "Coinbase.com",            "Target": "atm",                  "USD":    940_000_000},
            {"Source": "Coinbase.com",            "Target": "gambling",             "USD":    410_000_000},
            {"Source": "high risk exchange",      "Target": "Coinbase.com",         "USD":    640_000_000},
        ], "Counterparty flow Sankey"),
        "top_counterparties": _r([
            {"Counterparty": "Binance.com",     "Category": "exchange",
             "USD In": 4_120_000_000, "USD Out": 3_840_000_000,
             "Total Bilateral USD": 7_960_000_000, "Risk Flag": "✅ Regulated counterparty"},
            {"Counterparty": "Kraken.com",      "Category": "exchange",
             "USD In": 2_140_000_000, "USD Out": 1_920_000_000,
             "Total Bilateral USD": 4_060_000_000, "Risk Flag": "✅ Regulated counterparty"},
            {"Counterparty": "OKX.com",         "Category": "exchange",
             "USD In": 1_240_000_000, "USD Out": 1_180_000_000,
             "Total Bilateral USD": 2_420_000_000, "Risk Flag": "✅ Regulated counterparty"},
            {"Counterparty": "Bybit.com",       "Category": "exchange",
             "USD In": 980_000_000, "USD Out": 920_000_000,
             "Total Bilateral USD": 1_900_000_000, "Risk Flag": "✅ Regulated counterparty"},
            {"Counterparty": "Wintermute",      "Category": "institutional platform",
             "USD In": 740_000_000, "USD Out": 820_000_000,
             "Total Bilateral USD": 1_560_000_000, "Risk Flag": "✅ Regulated counterparty"},
            {"Counterparty": "Foundry USA Pool","Category": "mining",
             "USD In": 1_120_000_000, "USD Out": 0,
             "Total Bilateral USD": 1_120_000_000, "Risk Flag": "— other"},
            {"Counterparty": "MEXC.com",        "Category": "high risk exchange",
             "USD In": 420_000_000, "USD Out": 380_000_000,
             "Total Bilateral USD": 800_000_000, "Risk Flag": "⚠️ HIGH"},
            {"Counterparty": "Stake.com",       "Category": "gambling",
             "USD In": 180_000_000, "USD Out": 210_000_000,
             "Total Bilateral USD": 390_000_000, "Risk Flag": "— other"},
            {"Counterparty": "Hydra Marketplace","Category": "darknet market",
             "USD In": 8_400_000, "USD Out": 240_000,
             "Total Bilateral USD": 8_640_000, "Risk Flag": "⚠️ HIGH"},
            {"Counterparty": "Tornado Cash",    "Category": "mixing",
             "USD In": 240_000, "USD Out": 1_840_000,
             "Total Bilateral USD": 2_080_000, "Risk Flag": "⚠️ HIGH"},
        ], "Top counterparties"),
    },
    "phase4": {
        "self_hosted": _r([
            {"Direction": "Inflow",
             "Total USD (90d)": 27_840_000_000,
             "From Named Entities": 22_120_000_000,
             "From Unhosted Wallets": 5_720_000_000,
             "Unhosted %": 20.5,
             "Self-Hosted Profile": "🟡 Mixed — typical retail/institutional VASP shape"},
            {"Direction": "Outflow",
             "Total USD (90d)": 24_120_000_000,
             "From Named Entities": 19_840_000_000,
             "From Unhosted Wallets": 4_280_000_000,
             "Unhosted %": 17.7,
             "Self-Hosted Profile": "✅ Predominantly named-entity flows — institutional / B2B pattern"},
        ], "Self-hosted profile"),
    },
    "phase5": {
        "illicit": _r([
            {"Category": "high risk exchange", "USD (in + out, 90d)": 1_240_000_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "darknet market",     "USD (in + out, 90d)":    12_400_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "scam",               "USD (in + out, 90d)":     8_240_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "mixing",             "USD (in + out, 90d)":     2_080_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "sanctioned entity",  "USD (in + out, 90d)":     2_180_000, "Severity Tier": "🛑 SEVERE"},
        ], "Illicit exposure"),
        "illicit_trend": _r([
            {"Month": (datetime.now().replace(day=1) - timedelta(days=30*i)).strftime("%Y-%m-01"),
             "Illicit Exposure USD": 1_180_000_000 + (i * 8_000_000) - (i % 4) * 24_000_000}
            for i in range(11, -1, -1)
        ], "Illicit monthly trend"),
        "top_illicit": _r([
            {"Counterparty": "MEXC.com",         "Category": "high risk exchange",
             "USD In": 420_000_000, "USD Out": 380_000_000, "Total USD": 800_000_000,
             "Severity Tier": "⚠️ HIGH"},
            {"Counterparty": "Bitget",           "Category": "high risk exchange",
             "USD In": 180_000_000, "USD Out": 160_000_000, "Total USD": 340_000_000,
             "Severity Tier": "⚠️ HIGH"},
            {"Counterparty": "Hydra Marketplace","Category": "darknet market",
             "USD In": 8_400_000, "USD Out": 240_000, "Total USD": 8_640_000,
             "Severity Tier": "⚠️ HIGH"},
            {"Counterparty": "Garantex",         "Category": "sanctioned entity",
             "USD In": 1_240_000, "USD Out": 840_000, "Total USD": 2_080_000,
             "Severity Tier": "🛑 SEVERE"},
            {"Counterparty": "Tornado Cash",     "Category": "mixing",
             "USD In": 240_000, "USD Out": 1_840_000, "Total USD": 2_080_000,
             "Severity Tier": "⚠️ HIGH"},
        ], "Top illicit counterparties"),
        "velocity": _r([
            {"Category": "high risk exchange",
             "Prev 90d USD": 1_120_000_000, "Curr 90d USD": 1_240_000_000,
             "Delta USD": 120_000_000, "Delta %": 10.7,
             "Velocity Verdict": "— stable (within ±25%)"},
            {"Category": "sanctioned entity",
             "Prev 90d USD": 840_000, "Curr 90d USD": 2_180_000,
             "Delta USD": 1_340_000, "Delta %": 159.5,
             "Velocity Verdict": "🚨 Accelerating (>2x prior quarter)"},
            {"Category": "darknet market",
             "Prev 90d USD": 18_400_000, "Curr 90d USD": 12_400_000,
             "Delta USD": -6_000_000, "Delta %": -32.6,
             "Velocity Verdict": "🟢 Decelerating (<50% of prior)"},
            {"Category": "scam",
             "Prev 90d USD": 6_120_000, "Curr 90d USD": 8_240_000,
             "Delta USD": 2_120_000, "Delta %": 34.6,
             "Velocity Verdict": "⚠️ Increasing (>25%)"},
        ], "Adverse velocity"),
    },
    "phase7": {
        "peer_table": _r([
            {"Firm": "👉 Coinbase.com", "Role": "APPLICANT",
             "Total Received USD (all-time)": 142_400_000_000,
             "Current Balance USD": 2_840_000_000,
             "Days Since Last Activity": 1, "Days on Chain": 5089},
            {"Firm": "Kraken.com", "Role": "PEER",
             "Total Received USD (all-time)": 84_120_000_000,
             "Current Balance USD": 1_420_000_000,
             "Days Since Last Activity": 1, "Days on Chain": 4612},
            {"Firm": "Bitstamp.net", "Role": "PEER",
             "Total Received USD (all-time)": 22_140_000_000,
             "Current Balance USD": 380_000_000,
             "Days Since Last Activity": 1, "Days on Chain": 5210},
            {"Firm": "Gemini.com", "Role": "PEER",
             "Total Received USD (all-time)": 18_400_000_000,
             "Current Balance USD": 290_000_000,
             "Days Since Last Activity": 2, "Days on Chain": 3920},
        ], "Peer comparison"),
    },
}


# ---------------------------------------------------------------------------
# 🛑 BitBargain.co.uk — perimeter-hit case
# ---------------------------------------------------------------------------

BITBARGAIN = {
    "phase0": {
        "perimeter": _r([{
            "Perimeter Status": "🛑 PERIMETER HIT — primary-UK, not on FCA register",
            "Register Status": "unlicensed",
            "UK Confidence": "Almost certain",
        }], "Perimeter check"),
        "risk_tier": _r([{
            "Risk Tier": "🚨 Intensive (perimeter trigger)",
            "Total Received USD": 18_400_000,
            "FCA Register Status": "unlicensed",
            "UK Confidence": "Almost certain",
        }], "Risk tier"),
    },
    "phase1": {
        "time_on_chain": _r([{
            "First Observed": "2014-03-12",
            "Last Observed": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
            "Days On Chain": 4267,
            "Days Since Last Active": 2,
            "Maturity Signal": "🟢 5+ years on chain — established",
        }], "Time on chain"),
        "cluster_lineage": _r([], "Cluster lineage"),
    },
    "phase2": {
        "volume": _r([{
            "Window": "90-day window",
            "Observed In (USD)": 6_240_000,
            "Observed Out (USD)": 5_180_000,
            "Observed Total (USD)": 11_420_000,
            "Declared (USD)": 10_000_000,
            "Delta (USD)": 1_420_000,
            "Delta %": 14.2,
            "Status": "🟡 Moderate variance — within ±25%",
        }], "Volume reconciliation"),
        "cross_chain": _r([
            {"Chain": "bitcoin", "USD (in + out, 90d)": 11_420_000},
        ], "Cross-chain breakdown"),
    },
    "phase3": {
        "counterparty_mix": _r([
            {"Category": "p2p exchange",         "USD (in + out, 90d)": 4_840_000},
            {"Category": "no kyc exchange",      "USD (in + out, 90d)": 3_240_000},
            {"Category": "high risk exchange",   "USD (in + out, 90d)": 1_820_000},
            {"Category": "exchange",             "USD (in + out, 90d)":   980_000},
            {"Category": "darknet market",       "USD (in + out, 90d)":   420_000},
            {"Category": "mixing",               "USD (in + out, 90d)":    84_000},
            {"Category": "scam",                 "USD (in + out, 90d)":    32_000},
        ], "Counterparty mix"),
        "top_counterparties": _r([
            {"Counterparty": "LocalBitcoins.com", "Category": "p2p exchange",
             "USD In": 2_420_000, "USD Out": 2_420_000, "Total Bilateral USD": 4_840_000,
             "Risk Flag": "— other"},
            {"Counterparty": "Bisq",              "Category": "no kyc exchange",
             "USD In": 1_620_000, "USD Out": 1_620_000, "Total Bilateral USD": 3_240_000,
             "Risk Flag": "⚠️ HIGH"},
            {"Counterparty": "MEXC.com",          "Category": "high risk exchange",
             "USD In": 940_000, "USD Out": 880_000, "Total Bilateral USD": 1_820_000,
             "Risk Flag": "⚠️ HIGH"},
            {"Counterparty": "Hydra Marketplace", "Category": "darknet market",
             "USD In": 320_000, "USD Out": 100_000, "Total Bilateral USD": 420_000,
             "Risk Flag": "⚠️ HIGH"},
            {"Counterparty": "ChipMixer",         "Category": "mixing",
             "USD In": 42_000, "USD Out": 42_000, "Total Bilateral USD": 84_000,
             "Risk Flag": "⚠️ HIGH"},
        ], "Top counterparties"),
    },
    "phase5": {
        "illicit": _r([
            {"Category": "no kyc exchange",     "USD (in + out, 90d)": 3_240_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "high risk exchange",  "USD (in + out, 90d)": 1_820_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "darknet market",      "USD (in + out, 90d)":   420_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "mixing",              "USD (in + out, 90d)":    84_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "scam",                "USD (in + out, 90d)":    32_000, "Severity Tier": "⚠️ HIGH"},
        ], "Illicit exposure"),
        "top_illicit": _r([
            {"Counterparty": "Bisq",              "Category": "no kyc exchange",
             "USD In": 1_620_000, "USD Out": 1_620_000, "Total USD": 3_240_000, "Severity Tier": "⚠️ HIGH"},
            {"Counterparty": "MEXC.com",          "Category": "high risk exchange",
             "USD In": 940_000, "USD Out": 880_000, "Total USD": 1_820_000, "Severity Tier": "⚠️ HIGH"},
            {"Counterparty": "Hydra Marketplace", "Category": "darknet market",
             "USD In": 320_000, "USD Out": 100_000, "Total USD": 420_000, "Severity Tier": "⚠️ HIGH"},
        ], "Top illicit counterparties"),
    },
}


# ---------------------------------------------------------------------------
# 🟡 Binance.je — edge / enhanced supervision case
# ---------------------------------------------------------------------------

BINANCE_JE = {
    "phase0": {
        "perimeter": _r([{
            "Perimeter Status": "🟡 Not on FCA register, no primary-UK signal",
            "Register Status": "unlicensed",
            "UK Confidence": "no signal",
        }], "Perimeter check"),
        "risk_tier": _r([{
            "Risk Tier": "🟠 Intensive (size trigger)",
            "Total Received USD": 8_240_000_000,
            "FCA Register Status": "unlicensed",
            "UK Confidence": "no signal",
        }], "Risk tier"),
    },
    "phase1": {
        "time_on_chain": _r([{
            "First Observed": "2018-09-04",
            "Last Observed": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "Days On Chain": 2820,
            "Days Since Last Active": 1,
            "Maturity Signal": "🟢 5+ years on chain — established",
        }], "Time on chain"),
    },
    "phase2": {
        "volume": _r([{
            "Window": "90-day window",
            "Observed In (USD)": 620_000_000,
            "Observed Out (USD)": 540_000_000,
            "Observed Total (USD)": 1_160_000_000,
            "Declared (USD)": 1_000_000_000,
            "Delta (USD)": 160_000_000,
            "Delta %": 16.0,
            "Status": "🟡 Moderate variance — within ±25%",
        }], "Volume reconciliation"),
    },
    "phase3": {
        "counterparty_mix": _r([
            {"Category": "exchange",            "USD (in + out, 90d)": 720_000_000},
            {"Category": "institutional platform","USD (in + out, 90d)": 240_000_000},
            {"Category": "high risk exchange",  "USD (in + out, 90d)":  84_000_000},
            {"Category": "merchant services",   "USD (in + out, 90d)":  62_000_000},
            {"Category": "gambling",            "USD (in + out, 90d)":  28_000_000},
            {"Category": "scam",                "USD (in + out, 90d)":   1_240_000},
        ], "Counterparty mix"),
    },
    "phase5": {
        "illicit": _r([
            {"Category": "high risk exchange", "USD (in + out, 90d)": 84_000_000, "Severity Tier": "⚠️ HIGH"},
            {"Category": "scam",               "USD (in + out, 90d)":  1_240_000, "Severity Tier": "⚠️ HIGH"},
        ], "Illicit exposure"),
    },
}


# Final lookup keyed by the same string used in DEMO_CASES (with emoji prefix)
FIXTURES: dict[str, dict] = {
    "🟢 Coinbase (clean licensed)":       COINBASE,
    "🛑 BitBargain.co.uk (perimeter hit)": BITBARGAIN,
    "🟡 Binance.je (edge case)":           BINANCE_JE,
}
