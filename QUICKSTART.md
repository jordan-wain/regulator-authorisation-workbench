# Quickstart Guide

## Local Development

```bash
cd streamlit_app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DATA_SOLUTIONS_API_KEY="your-key"
export COMPANIES_HOUSE_API_KEY="your-key"
streamlit run app.py
```

## Streamlit Community Cloud Deployment

1. **Push** the `streamlit_app/` directory to a GitHub repo.
2. Go to [https://share.streamlit.io](https://share.streamlit.io).
3. **Connect** the repo and set `app.py` as the entrypoint.
4. In **Settings → Secrets**, add your secrets using the format from `.streamlit/secrets.toml.example`:

   ```toml
   DATA_SOLUTIONS_API_KEY = "your-ds-api-key"
   COMPANIES_HOUSE_API_KEY = "your-ch-api-key"
   ```

5. Click **Deploy**. The app will be live at a `*.streamlit.app` URL you can share with colleagues and regulators.

## API Key Notes

- **DATA_SOLUTIONS_API_KEY** — Your Chainalysis Data Solutions API key.
- **COMPANIES_HOUSE_API_KEY** — UK Companies House API key for firm lookups.

The app checks `os.environ` first, then falls back to `st.secrets`, so both local env vars and Streamlit Cloud secrets work seamlessly.
