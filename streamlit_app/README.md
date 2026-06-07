# UK FCA Firm Authorisation Workbench — Streamlit App

App-layer wrapper around Data Solutions dashboard **4015** that adds the
capabilities the dashboard intentionally cannot express (per the
`productisation_levels.md` framing):

- **Per-case state persistence** — every input + every query result is stored
  in a local SQLite DB at `streamlit_app/data/cases.db`, so closing the
  browser and reopening it later lands you back where you left off.
- **Structured intake form** — sidebar form with all 26+ application
  parameters grouped by FCA application-form section.
- **Companies House PSC + officers lookup** — button-triggered call into the
  live Companies House API (search → top hit → PSC + officers).
- **Evidence-pack export** — single-click HTML evidence pack covering all
  10 phases plus the audit log; PDF if WeasyPrint is installed locally.
- **11-tab phase walkthrough** — mirrors the dashboard layout so case
  officers familiar with dashboard 4015 see the same shape here.

> The SQL queries this app runs are direct ports of the dashboard tiles —
> see `utils/queries.py`. They hit the same `cross_chain.*` schema via the
> Data Solutions analytical SQL API.

---

## Requirements

Python 3.10+ and the packages in `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r streamlit_app/requirements.txt
```

### Environment variables

| Variable | Purpose | Required |
|---|---|---|
| `DATA_SOLUTIONS_API_KEY` | Auth for the DS analytical SQL API | ✅ |
| `DATA_SOLUTIONS_BASE_URL` | DS API base URL (default `https://api.transpose.io`) | optional |
| `COMPANIES_HOUSE_API_KEY` | Auth for Companies House REST API | for CH lookup |

Set them in a `.env`, your shell, or your deployment platform's secrets
manager. The app degrades gracefully — DS query buttons return an error
message if `DATA_SOLUTIONS_API_KEY` is missing; the Companies House panel
shows an error if its key is missing.

---

## Run locally

```bash
streamlit run streamlit_app/app.py
```

The app opens at `http://localhost:8501`. On first run it creates
`streamlit_app/data/cases.db` automatically.

---

## Project structure

```
streamlit_app/
├── app.py                # Sidebar case mgmt + intake form + 11 tabs
├── requirements.txt
├── README.md             # this file
├── utils/
│   ├── __init__.py
│   ├── data.py           # DS query wrapper, CH API, SQLite, FCA lists
│   ├── queries.py        # All SQL ported from dashboard 4015
│   └── pdf_export.py     # Evidence-pack renderer
└── data/                 # SQLite DB (auto-created on first run)
```

### `utils/data.py`

- `run_ds_query(sql)` — POST to `${DS_BASE_URL}/sql/analytical` with
  `Api-Key` header, returns a `pandas.DataFrame`.
- `companies_house_lookup(name)` — wraps search → PSC → officers into a
  single call.
- `check_fca_register(name)` / `check_fca_warnings(name)` — offline
  bidirectional substring match against the bundled FCA lists.
- `init_db / list_cases / load_case / save_case / delete_case` — SQLite
  persistence.
- `log_audit / get_audit_log` — append-only audit trail.

### `utils/queries.py`

One function per dashboard tile family. Each returns a complete SQL string
with parameters substituted as quoted literals (no template tags) so the
result is safe to send straight to the DS endpoint:

| Function | Dashboard tile |
|---|---|
| `sql_perimeter_check(applicant, fca_registered)` | C4 |
| `sql_sanctions_screen(declared_wallets)` | C5 |
| `sql_risk_tier(applicant, fca_registered)` | C8 |
| `sql_time_on_chain(applicant)` | P1.2 |
| `sql_osint(applicant, declared_wallets)` | P1.5 |
| `sql_volume_reconciliation(applicant, window_days, declared)` | P2.1 |
| `sql_counterparty_mix(applicant)` | P3.1 |
| `sql_illicit_exposure(applicant)` | P5.1 |
| `sql_peer_comparison(applicant, peers)` | P7.1 |

All queries that scan exposure tables include
`asset_id IN (SELECT asset_id FROM utils.assets)` to drop mispriced
tokens, per `scope/build_conventions.md` §3.

---

## Deployment

### Streamlit Community Cloud (recommended for demos)

1. Push the repo (or just the `streamlit_app/` directory) to GitHub.
2. Connect at <https://streamlit.io/cloud> → "New app".
3. Main file path: `streamlit_app/app.py`.
4. Add `DATA_SOLUTIONS_API_KEY` and `COMPANIES_HOUSE_API_KEY` under
   **Settings → Secrets**.
5. Deploy.

> The SQLite DB lives on the container's ephemeral filesystem on Streamlit
> Cloud — fine for a demo, **not** suitable for real case data. For
> persistent storage, swap `utils/data.py` SQLite calls for a managed DB
> (Postgres, etc.).

### Internal Chainalysis hosting

Build a container image:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY streamlit_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY streamlit_app /app/streamlit_app
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Mount a persistent volume at `/app/streamlit_app/data` if you need case
state to survive restarts.

---

## Relationship to dashboard 4015

This app is the **app-layer** in the productisation framing — same SQL,
plus the state/audit/export layer that a Metabase dashboard can't host.
Most users will keep working in the dashboard; this app exists to validate
what the app-layer experience looks like and to host the FCA-form-driven
intake (which the dashboard captures as URL params but doesn't persist).

See `scope/productisation_levels.md` and
`scope/fca_application_alignment.md` for design rationale.
