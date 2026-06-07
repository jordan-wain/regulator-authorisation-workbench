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

The app will open at `http://localhost:8501`.

---

## Streamlit Community Cloud Deployment

### Prerequisites

- A GitHub account with access to the `jordan-wain/regulator-authorisation-workbench` repo
- A free account at [share.streamlit.io](https://share.streamlit.io) (sign up with your GitHub account)
- Your API keys:
  - `DATA_SOLUTIONS_API_KEY` — Chainalysis Data Solutions
  - `COMPANIES_HOUSE_API_KEY` — UK Companies House

### Step 1: Ensure the repo is ready

Make sure `app.py`, `requirements.txt`, and all application code have been pushed to the repo. The repo root should contain at minimum:

```
app.py                          ← Streamlit entrypoint
requirements.txt                ← Python dependencies
.streamlit/config.toml          ← Theme and server config
.streamlit/secrets.toml.example ← Secret template (not the real secrets)
utils/
  __init__.py
  data.py
```

> ⚠️ **Never commit `.streamlit/secrets.toml`** — it is in `.gitignore` for a reason. Secrets are configured in the Streamlit Cloud dashboard instead.

### Step 2: Sign in to Streamlit Cloud

1. Go to [https://share.streamlit.io](https://share.streamlit.io).
2. Click **Sign in with GitHub**.
3. Authorize Streamlit to access your GitHub account if prompted.

### Step 3: Create a new app

1. Click **New app** (top-right corner).
2. Under **Repository**, select `jordan-wain/regulator-authorisation-workbench`.
   - If the repo doesn't appear, click **Paste GitHub URL** and enter:
     `https://github.com/jordan-wain/regulator-authorisation-workbench`
3. **Branch**: select `main`.
4. **Main file path**: enter `app.py`.
5. Click **Advanced settings…** before deploying (see Step 4).

### Step 4: Add secrets

1. In the **Advanced settings** dialog (or after deployment via **Settings**):
   - Click the **Secrets** section.
2. Paste the following into the secrets text box, replacing the placeholder values with your real keys:

   ```toml
   DATA_SOLUTIONS_API_KEY = "your-actual-ds-api-key"
   COMPANIES_HOUSE_API_KEY = "your-actual-ch-api-key"
   ```

3. Click **Save**.

> These secrets are encrypted and only available to your app at runtime via `st.secrets`. They are never exposed in the repo or logs.

### Step 5: Deploy

1. Click **Deploy!**
2. Streamlit Cloud will:
   - Clone your repo
   - Install dependencies from `requirements.txt`
   - Apply the theme from `.streamlit/config.toml`
   - Start the app
3. Wait for the build to complete (typically 2–5 minutes on first deploy).
4. Your app will be live at a URL like:
   ```
   https://regulator-authorisation-workbench.streamlit.app
   ```

### Step 6: Share the URL

- Copy the app URL and share it directly with colleagues or regulators.
- Since this is a **private repo**, only people with the URL can access the deployed app by default.
- To restrict access further, go to **Settings → Sharing** in the Streamlit Cloud dashboard:
  - **Only people with the link** — anyone with the URL can view (default)
  - **Only specific people** — restrict to a list of email addresses

### Updating the app

Any push to the `main` branch will automatically trigger a redeploy. There's no manual step — just `git push` and Streamlit Cloud picks up the changes within a few seconds.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| App fails to start | Check **Manage app → Logs** in the bottom-right corner for error output |
| `KeyError` on secrets | Ensure secrets are saved in **Settings → Secrets** using the exact key names above |
| Repo not visible | Make sure your GitHub account has access to the private repo, and that Streamlit has been authorized for the `jordan-wain` account |
| Dependencies fail to install | Ensure `requirements.txt` is at the repo root and all packages are spelled correctly |
| Theme not applying | Confirm `.streamlit/config.toml` is committed and at the correct path |

---

## API Key Notes

- **DATA_SOLUTIONS_API_KEY** — Your Chainalysis Data Solutions API key.
- **COMPANIES_HOUSE_API_KEY** — UK Companies House API key for firm lookups.

The app checks `os.environ` first, then falls back to `st.secrets`, so both local env vars and Streamlit Cloud secrets work seamlessly.
