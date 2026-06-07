# UK FCA Firm Authorisation Workbench

A Streamlit application for investigating and assessing UK Financial Conduct Authority (FCA) firm authorisation cases, built on **Chainalysis Data Solutions**.

## What This Is

This is the interactive front-end for the **Regulator Authorisation Workbench** — a tool that helps compliance analysts and regulators:

- Screen firms applying for FCA authorisation against blockchain-derived risk intelligence from Chainalysis Data Solutions
- Cross-reference applicant data with UK Companies House records
- Track and manage authorisation cases through a structured workflow
- Generate assessment summaries suitable for sharing with regulators

## Architecture

The app is a pure **Streamlit** application that calls:

- **Chainalysis Data Solutions API** — for blockchain analytics, entity risk exposure, and cluster data
- **UK Companies House API** — for corporate registry lookups and officer/filing data

## Getting Started

See [QUICKSTART.md](QUICKSTART.md) for local setup and Streamlit Community Cloud deployment instructions.

## Secrets

The app requires two API keys, configured via environment variables or Streamlit secrets:

| Secret | Description |
|--------|-------------|
| `DATA_SOLUTIONS_API_KEY` | Chainalysis Data Solutions API key |
| `COMPANIES_HOUSE_API_KEY` | UK Companies House API key |

See `.streamlit/secrets.toml.example` for the template.
