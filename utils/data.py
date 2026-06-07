"""
Data utilities for the UK FCA Firm Authorisation Workbench.
Handles API key loading and data access for Chainalysis Data Solutions
and UK Companies House.
"""

import os
import streamlit as st

# API keys: check env vars first, fall back to Streamlit secrets (for Cloud deployment)
DS_API_KEY = os.environ.get("DATA_SOLUTIONS_API_KEY") or st.secrets.get("DATA_SOLUTIONS_API_KEY", "")
CH_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY") or st.secrets.get("COMPANIES_HOUSE_API_KEY", "")
