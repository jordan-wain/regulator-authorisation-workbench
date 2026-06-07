"""
🇬🇧 UK FCA — Firm Authorisation Workbench
Built on Chainalysis Data Solutions
"""

import datetime

import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data import (
    save_case,
    load_case,
    list_cases,
    ch_search,
    ch_psc,
    check_fca_register,
    check_fca_warnings,
    generate_evidence_pack_bytes,
)
from utils.queries import (
    sql_risk_tier,
    sql_perimeter_check,
    sql_sanctions_screen,
    sql_time_on_chain,
    sql_osint,
    sql_volume_reconciliation,
    sql_counterparty_mix,
    sql_illicit_exposure,
    sql_peer_comparison,
)

# ═══════════════════════════════════════════════════════════════════════
# Page config
# ═══════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="🇬🇧 UK FCA — Firm Authorisation Workbench",
    layout="wide",
)

# ═══════════════════════════════════════════════════════════════════════
# Defaults & session state
# ═══════════════════════════════════════════════════════════════════════
DEFAULTS: dict = {
    "case_id": "",
    "applicant_name": "",
    "applicant_legal_entity": "",
    "regime_applied_for": "",
    "declared_ubos": "",
    "case_officer": "",
    "submission_date": str(datetime.date.today()),
    "prior_denials_yn": "No",
    "prior_denial_detail": "",
    "declared_wallets": "",
    "declared_affiliated_firms": "",
    "declared_territories": "",
    "declared_volume_usd": 0.0,
    "declared_user_count": 0,
    "declared_balance_usd": 0.0,
    "declared_assets": "",
    "declared_business_model": "",
    "declared_custody_arrangement": "",
    "licences_held_elsewhere": "",
    "declared_peer_cohort": "",
}

if "case" not in st.session_state:
    st.session_state.case = DEFAULTS.copy()

c = st.session_state.case  # shorthand

# ═══════════════════════════════════════════════════════════════════════
# Sidebar — case management & structured intake form
# ═══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("📁 Case Management")

    existing = list_cases()
    if existing:
        sel = st.selectbox("Load existing case", ["— new —"] + existing)
        if sel != "— new —" and st.button("📂 Load"):
            loaded = load_case(sel)
            if loaded:
                st.session_state.case = {**DEFAULTS, **loaded}
                st.rerun()

    if st.button("🆕 New Case"):
        st.session_state.case = DEFAULTS.copy()
        st.rerun()

    st.divider()
    st.subheader("📝 Intake Form")

    c["case_id"] = st.text_input("Case ID", value=c["case_id"])
    c["applicant_name"] = st.text_input("Applicant Name", value=c["applicant_name"])
    c["applicant_legal_entity"] = st.text_input("Legal Entity", value=c["applicant_legal_entity"])
    c["regime_applied_for"] = st.text_input("Regime Applied For", value=c["regime_applied_for"])
    c["declared_ubos"] = st.text_area("Declared UBOs", value=c["declared_ubos"], height=68)
    c["case_officer"] = st.text_input("Case Officer", value=c["case_officer"])
    c["submission_date"] = st.text_input("Submission Date", value=c["submission_date"])
    c["prior_denials_yn"] = st.selectbox(
        "Prior Denials?", ["No", "Yes"],
        index=0 if c["prior_denials_yn"] == "No" else 1,
    )
    if c["prior_denials_yn"] == "Yes":
        c["prior_denial_detail"] = st.text_area(
            "Prior Denial Detail", value=c["prior_denial_detail"], height=68,
        )
    c["declared_wallets"] = st.text_area(
        "Declared Wallets (one per line)", value=c["declared_wallets"], height=100,
    )
    c["declared_affiliated_firms"] = st.text_area(
        "Affiliated Firms", value=c["declared_affiliated_firms"], height=68,
    )
    c["declared_territories"] = st.text_input("Territories", value=c["declared_territories"])
    c["declared_volume_usd"] = st.number_input(
        "Declared Volume (USD)", value=float(c["declared_volume_usd"]),
        min_value=0.0, format="%.2f",
    )
    c["declared_user_count"] = st.number_input(
        "Declared User Count", value=int(c["declared_user_count"]), min_value=0,
    )
    c["declared_balance_usd"] = st.number_input(
        "Declared Balance (USD)", value=float(c["declared_balance_usd"]),
        min_value=0.0, format="%.2f",
    )
    c["declared_assets"] = st.text_input("Declared Assets", value=c["declared_assets"])
    c["declared_business_model"] = st.text_input("Business Model", value=c["declared_business_model"])
    c["declared_custody_arrangement"] = st.text_area(
        "Custody Arrangement", value=c["declared_custody_arrangement"], height=68,
    )
    c["licences_held_elsewhere"] = st.text_input(
        "Licences Held Elsewhere", value=c["licences_held_elsewhere"],
    )
    c["declared_peer_cohort"] = st.text_input("Peer Cohort", value=c["declared_peer_cohort"])

    st.divider()
    if st.button("💾 Save Case", type="primary"):
        if c["case_id"]:
            save_case(c["case_id"], c)
            st.success(f"Saved: {c['case_id']}")
        else:
            st.error("Enter a Case ID before saving.")

# ═══════════════════════════════════════════════════════════════════════
# Guard — require an applicant name
# ═══════════════════════════════════════════════════════════════════════
name = c["applicant_name"]
if not name:
    st.info("👈 Enter an applicant name in the sidebar to begin analysis.")
    st.stop()

st.title(f"🇬🇧 {name}")
st.caption(
    f"Case: {c['case_id'] or '(unsaved)'}  ·  "
    f"Officer: {c['case_officer'] or '—'}  ·  "
    f"Submitted: {c['submission_date']}"
)

# ═══════════════════════════════════════════════════════════════════════
# Tabs
# ═══════════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📋 Summary",
    "0 · Perimeter",
    "1 · Time & OSINT",
    "2 · Volume",
    "3 · Counterparties",
    "4 · Custody",
    "5 · Illicit Exposure",
    "6 · Stablecoin",
    "7 · Peer Comparison",
    "8 · Decision",
    "9 · Post-Decision",
])

# ───────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Hard-Stop Indicators")
    hs1, hs2, hs3 = st.columns(3)

    with hs1:
        st.markdown("**🔍 Perimeter Check**")
        try:
            reg_df = check_fca_register(name)
            if reg_df.empty:
                st.warning("⚠️ No FCA register match found")
            else:
                st.success(f"✅ {len(reg_df)} match(es) found")
                st.dataframe(reg_df, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    with hs2:
        st.markdown("**⚠️ FCA Warnings**")
        try:
            warn_df = check_fca_warnings(name)
            if warn_df.empty:
                st.success("✅ No FCA warnings found")
            else:
                st.error(f"🚨 {len(warn_df)} warning(s) found")
                st.dataframe(warn_df, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    with hs3:
        st.markdown("**📊 Risk Tier**")
        try:
            risk_df = sql_risk_tier(name)
            if risk_df.empty:
                st.info("No risk-tier data")
            else:
                st.dataframe(risk_df, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")

    st.divider()
    st.subheader("Outstanding Inputs")
    checks = {
        "Case ID": bool(c["case_id"]),
        "Applicant Name": bool(name),
        "Legal Entity": bool(c["applicant_legal_entity"]),
        "Regime": bool(c["regime_applied_for"]),
        "Declared UBOs": bool(c["declared_ubos"]),
        "Case Officer": bool(c["case_officer"]),
        "Declared Wallets": bool(c["declared_wallets"]),
        "Business Model": bool(c["declared_business_model"]),
        "Custody Arrangement": bool(c["declared_custody_arrangement"]),
    }
    for label, ok in checks.items():
        st.markdown(f"{'✅' if ok else '❌'} {label}")

    st.divider()
    st.subheader("Peer Comparator")
    try:
        peer_df = sql_peer_comparison(name)
        if not peer_df.empty:
            st.dataframe(peer_df, use_container_width=True)
        else:
            st.info("No peer comparison data available.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 0 — Perimeter
# ───────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("Phase 0 · Perimeter Check")

    # DS perimeter
    st.markdown("#### DS Perimeter Check")
    try:
        peri_df = sql_perimeter_check(name)
        if not peri_df.empty:
            st.dataframe(peri_df, use_container_width=True)
        else:
            st.info("No perimeter data found in Data Solutions.")
    except Exception as exc:
        st.error(f"Error: {exc}")

    # Sanctions screen
    st.markdown("#### Sanctions Screen")
    wallets = [w.strip() for w in c["declared_wallets"].splitlines() if w.strip()]
    if wallets:
        try:
            sanc_df = sql_sanctions_screen(wallets)
            if sanc_df.empty:
                st.success("✅ No sanctions hits for declared wallets")
            else:
                st.error("🚨 Sanctions match found")
                st.dataframe(sanc_df, use_container_width=True)
        except Exception as exc:
            st.error(f"Error: {exc}")
    else:
        st.warning("No declared wallets to screen.")

    # FCA warnings
    st.markdown("#### FCA Warnings")
    try:
        w_df = check_fca_warnings(name)
        if w_df.empty:
            st.success("✅ No FCA warnings")
        else:
            st.error(f"🚨 {len(w_df)} warning(s)")
            st.dataframe(w_df, use_container_width=True)
    except Exception as exc:
        st.error(f"Error: {exc}")

    # Companies House PSC
    st.markdown("#### Companies House — PSC Lookup")
    if st.button("🔍 Search Companies House", key="ch_search_btn"):
        query = c["applicant_legal_entity"] or name
        try:
            results = ch_search(query)
            if not results:
                st.info("No Companies House results found.")
            else:
                for r in results:
                    title = r.get("title", "Unknown")
                    co_num = r.get("company_number", "N/A")
                    with st.expander(f"{title} — {co_num}"):
                        st.json(r)
                        if st.button(f"📋 Get PSCs for {co_num}", key=f"psc_{co_num}"):
                            pscs = ch_psc(co_num)
                            if pscs:
                                for psc in pscs:
                                    st.json(psc)
                            else:
                                st.info("No PSCs found for this company.")
        except Exception as exc:
            st.error(f"Companies House error: {exc}")

    # Risk tier
    st.markdown("#### Risk Tier")
    try:
        rt_df = sql_risk_tier(name)
        if not rt_df.empty:
            st.dataframe(rt_df, use_container_width=True)
        else:
            st.info("No risk-tier data.")
    except Exception as exc:
        st.error(f"Error: {exc}")

    # Prior-denial attestation
    st.markdown("#### Prior Denial Attestation")
    if c["prior_denials_yn"] == "Yes":
        st.warning(f"⚠️ Prior denials declared: {c['prior_denial_detail']}")
    else:
        st.success("✅ No prior denials declared.")

# ───────────────────────────────────────────────────────────────────────
# PHASE 1 — Time on Chain & OSINT
# ───────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("Phase 1 · Time on Chain & OSINT")

    st.markdown("#### Time on Chain")
    try:
        time_df = sql_time_on_chain(name)
        if not time_df.empty:
            st.dataframe(time_df, use_container_width=True)
        else:
            st.info("No time-on-chain data.")
    except Exception as exc:
        st.error(f"Error: {exc}")

    st.markdown("#### OSINT Scan")
    try:
        osint_df = sql_osint(name)
        if not osint_df.empty:
            st.dataframe(osint_df, use_container_width=True)
        else:
            st.info("No OSINT data found.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 2 — Volume Reconciliation
# ───────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Phase 2 · Volume Reconciliation")
    try:
        vol_df = sql_volume_reconciliation(name)
        if not vol_df.empty:
            st.dataframe(vol_df, use_container_width=True)

            st.markdown("#### Declared vs Observed")
            obs_vol = (
                vol_df["total_received_usd"].astype(float).sum()
                if "total_received_usd" in vol_df.columns
                else 0.0
            )
            decl_vol = float(c["declared_volume_usd"])
            delta = obs_vol - decl_vol
            delta_pct = (delta / decl_vol * 100) if decl_vol else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Declared Volume (USD)", f"${decl_vol:,.2f}")
            m2.metric("Observed Volume (USD)", f"${obs_vol:,.2f}")
            m3.metric("Delta", f"${delta:,.2f}", f"{delta_pct:+.1f}%")
        else:
            st.info("No volume data found.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 3 — Counterparty Mix
# ───────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Phase 3 · Counterparty Mix")
    try:
        cp_df = sql_counterparty_mix(name)
        if not cp_df.empty:
            fig = px.pie(
                cp_df,
                values=cp_df.columns[-1],
                names=cp_df.columns[0],
                title=f"Counterparty Mix — {name}",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(cp_df, use_container_width=True)
        else:
            st.info("No counterparty data found.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 4 — Custody Attestation
# ───────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Phase 4 · Custody Attestation")
    if c["declared_custody_arrangement"]:
        st.info(
            f"**Declared Custody Arrangement:**\n\n"
            f"{c['declared_custody_arrangement']}"
        )
    else:
        st.warning("⚠️ No custody arrangement declared. "
                    "Request this from the applicant before proceeding.")

# ───────────────────────────────────────────────────────────────────────
# PHASE 5 — Illicit Exposure
# ───────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Phase 5 · Illicit Exposure")
    try:
        ill_df = sql_illicit_exposure(name)
        if not ill_df.empty:
            st.dataframe(ill_df, use_container_width=True)

            cat_col = ill_df.columns[0]
            val_col = ill_df.columns[-1]
            fig = px.bar(
                ill_df,
                x=cat_col,
                y=val_col,
                title=f"Illicit Exposure by Category — {name}",
                color=cat_col,
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.success("✅ No illicit exposure detected.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 6 — Stablecoin Framing
# ───────────────────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("Phase 6 · Stablecoin Framing")
    st.markdown(
        """
        **Regulatory context — stablecoin activity assessment**

        Under the UK Financial Services and Markets Act 2023, stablecoin-related
        activities (issuance, custody, and use as a means of payment) are brought
        within the FCA's regulatory perimeter.

        When assessing the applicant's stablecoin activity, consider:

        1. **Proportion of volume** — What share of the applicant's total on-chain
           volume involves fiat-referenced stablecoins (USDT, USDC, DAI, etc.)?
        2. **Issuance vs. secondary market** — Is the applicant issuing stablecoins
           or transacting in third-party issued tokens?
        3. **Redemption pathway** — Does the applicant maintain a clear fiat
           redemption pathway, and are reserves adequately attested?
        4. **Cross-border flow** — Are stablecoin flows concentrated in any
           high-risk jurisdictions identified by the FATF or OFSI?

        *Review the Volume (Phase 2) and Counterparty (Phase 3) tabs to quantify
        stablecoin exposure. Flag any material inconsistency between declared
        activity and observed on-chain stablecoin flows.*
        """
    )

# ───────────────────────────────────────────────────────────────────────
# PHASE 7 — Peer Comparison
# ───────────────────────────────────────────────────────────────────────
with tabs[8]:
    st.subheader("Phase 7 · Peer Comparison")
    try:
        peer_df = sql_peer_comparison(name)
        if not peer_df.empty:
            st.dataframe(peer_df, use_container_width=True)
        else:
            st.info("No peer comparison data available.")
    except Exception as exc:
        st.error(f"Error: {exc}")

# ───────────────────────────────────────────────────────────────────────
# PHASE 8 — Decision
# ───────────────────────────────────────────────────────────────────────
with tabs[9]:
    st.subheader("Phase 8 · Decision")

    outcome = st.selectbox(
        "Outcome",
        ["— select —", "Approve", "Approve with Conditions", "Refer", "Reject"],
    )
    analyst_note = st.text_area("Analyst Note", height=150)
    conditions = st.text_area("Conditions (if applicable)", height=100)
    second_reviewer = st.text_input("Second Reviewer")

    # Inconsistency challenge logic
    if outcome in ("Approve", "Approve with Conditions"):
        challenges: list[str] = []
        if c["prior_denials_yn"] == "Yes":
            challenges.append(
                "⚠️ Prior denials declared — confirm rationale for approval."
            )
        if not c["declared_wallets"]:
            challenges.append(
                "⚠️ No wallets declared — cannot verify on-chain activity."
            )
        if not c["declared_custody_arrangement"]:
            challenges.append(
                "⚠️ No custody arrangement declared."
            )
        try:
            ill_check = sql_illicit_exposure(name)
            if not ill_check.empty:
                challenges.append(
                    "🚨 Illicit exposure detected — review Phase 5 before approving."
                )
        except Exception:
            pass

        if challenges:
            st.warning("**Inconsistency Challenges:**")
            for ch in challenges:
                st.markdown(f"- {ch}")

    if st.button("📝 Record Decision", type="primary"):
        if outcome == "— select —":
            st.error("Select an outcome first.")
        else:
            c["decision_outcome"] = outcome
            c["decision_analyst_note"] = analyst_note
            c["decision_conditions"] = conditions
            c["decision_second_reviewer"] = second_reviewer
            c["decision_timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
            if c["case_id"]:
                save_case(c["case_id"], c)
                st.success("Decision recorded and case saved.")
            else:
                st.warning("Decision stored in session only — save the case to persist.")

# ───────────────────────────────────────────────────────────────────────
# PHASE 9 — Post-Decision
# ───────────────────────────────────────────────────────────────────────
with tabs[10]:
    st.subheader("Phase 9 · Post-Decision")

    # Re-screening cadence
    st.markdown("#### Re-Screening Cadence")
    cadence_map = {
        "Low": "Annual",
        "Standard": "Semi-annual",
        "High": "Quarterly",
        "Critical": "Monthly",
    }
    try:
        rt = sql_risk_tier(name)
        tier_label = "Standard"
        if not rt.empty and "entity_category" in rt.columns:
            cat = str(rt.iloc[0]["entity_category"]).lower()
            if any(k in cat for k in ("sanction", "ransomware", "stolen", "terrorism")):
                tier_label = "Critical"
            elif any(k in cat for k in ("scam", "fraud", "darknet", "mixing")):
                tier_label = "High"
            elif any(k in cat for k in ("exchange", "service")):
                tier_label = "Low"
    except Exception:
        tier_label = "Standard"
    st.metric("Recommended Re-Screening Cadence", cadence_map[tier_label])

    # Conditions handoff
    st.markdown("#### Conditions Handoff")
    conds = c.get("decision_conditions", "")
    if conds:
        st.info(conds)
    else:
        st.info("No conditions set.")

    # Evidence-pack download
    st.markdown("#### Evidence Pack")
    pack_bytes = generate_evidence_pack_bytes(c)
    st.download_button(
        label="📥 Download Evidence Pack",
        data=pack_bytes,
        file_name=f"evidence_pack_{c['case_id'] or 'draft'}.json",
        mime="application/json",
    )
