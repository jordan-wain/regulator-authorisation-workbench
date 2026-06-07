"""Evidence-pack export — FCA-branded HTML/PDF renderer.

Renders a case's full state to a single self-contained HTML document with:
  - FCA-maroon header bar with embedded logo (base64, no external assets)
  - Section anchors per phase
  - Print-friendly CSS (page-break-inside avoid, footer on each page)
  - Prominent "PROTOTYPE — DO NOT FILE" banner (we don't have FCA endorsement)
  - Optional PDF rendering via WeasyPrint when installed

If you ever take this in front of actual FCA staff: replace the FCA logo
with a Chainalysis Workbench mark and drop the FCA-branded header bar —
otherwise the document implies endorsement we don't have.
"""
from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "fca_logo.png"
FCA_PURPLE = "#701B45"
FCA_PURPLE_DARK = "#5C1538"


def _embedded_logo_data_uri() -> str:
    """Return the FCA logo as a base64 data: URI so the HTML pack is fully
    self-contained (no external image fetch when emailed / archived)."""
    if not _LOGO_PATH.exists():
        return ""
    try:
        b = _LOGO_PATH.read_bytes()
        return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        return ""


def _escape(value: Any) -> str:
    """Render any Python value as escaped HTML, recursively for dict/list."""
    if value is None:
        return "<em>—</em>"
    if isinstance(value, (list, tuple)):
        if not value:
            return "<em>(empty)</em>"
        return "<ul>" + "".join(f"<li>{_escape(v)}</li>" for v in value) + "</ul>"
    if isinstance(value, dict):
        rows = "".join(
            f"<tr><th>{html.escape(str(k))}</th><td>{_escape(v)}</td></tr>"
            for k, v in value.items()
        )
        return f"<table class='kv'>{rows}</table>"
    return html.escape(str(value))


# ---------------------------------------------------------------------------
# Number formatting — mirror of streamlit_app/app.py fmt_usd + styled_dataframe
# so the evidence pack reads the same as on-screen tables.
# ---------------------------------------------------------------------------

def _fmt_usd(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return html.escape(str(v))
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e12: return f"{sign}${x/1e12:.2f} T"
    if x >= 1e9:  return f"{sign}${x/1e9:.2f} B"
    if x >= 1e6:  return f"{sign}${x/1e6:.2f} M"
    if x >= 1e3:  return f"{sign}${x/1e3:.1f} K"
    return f"{sign}${x:,.0f}"


def _fmt_int(v) -> str:
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _fmt_pct(v) -> str:
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _column_formatter(col: str):
    """Pick a per-column formatter from the column name. None means default."""
    cl = col.lower()
    if "usd" in cl or "balance" in cl:
        return _fmt_usd
    if col.endswith("%") or "%ile" in col or "Pct" in col:
        return _fmt_pct
    # Word-boundary-ish checks so 'Count' doesn't match 'Counterparty', etc.
    int_tokens = ("Days", "Count", "Findings", "Tx",
                  "Clusters", "Addresses Affected", "N (", "Transactions")
    tokens_in_col = set(col.replace("(", " ").replace(")", " ").split())
    if any(t in tokens_in_col for t in int_tokens):
        return _fmt_int
    # 'Tx' as a prefix on a token (Tx-Count etc.)
    if any(col.startswith(t + " ") or col == t for t in int_tokens):
        return _fmt_int
    # Anything that *starts with* "High-Confidence" / "Low-Confidence" etc.
    if col.startswith(("High-Confidence", "Low-Confidence", "Cohort N")):
        return _fmt_int
    return None

def _render_result_block(saved: dict) -> str:
    """Render a single saved query result as a labelled mini-table."""
    label = html.escape(saved.get("label") or "Result")
    records = saved.get("records") or []
    ran_at = html.escape(saved.get("ran_at") or "—")
    if not records:
        body = "<p class='empty'><em>No rows returned.</em></p>"
    else:
        cols = saved.get("columns") or list(records[0].keys())
        col_formatters = {c: _column_formatter(c) for c in cols}
        thead = "<tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in cols) + "</tr>"
        rows = []
        for r in records[:50]:  # cap at 50 rows per tile in the pack
            cells = []
            for c in cols:
                v = r.get(c)
                if v is None:
                    cells.append("<td class='muted'>—</td>")
                    continue
                fmt = col_formatters.get(c)
                if fmt is not None:
                    cells.append(f"<td class='num'>{html.escape(fmt(v))}</td>")
                elif isinstance(v, (int, float)):
                    cells.append(f"<td class='num'>{html.escape(f'{v:,}' if isinstance(v, int) else str(v))}</td>")
                else:
                    cells.append(f"<td>{html.escape(str(v))}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        truncated = ""
        if len(records) > 50:
            truncated = f"<p class='trunc'>… showing first 50 of {len(records)} rows.</p>"
        body = (
            f"<table class='data'><thead>{thead}</thead>"
            f"<tbody>{''.join(rows)}</tbody></table>{truncated}"
        )
    return (
        f"<div class='result'>"
        f"<div class='result-header'>"
        f"<span class='result-label'>{label}</span>"
        f"<span class='result-meta'>ran {ran_at}</span>"
        f"</div>{body}</div>"
    )


def _render_phase_section(phase_key: str, phase_title: str, phase_state: dict) -> str:
    """Render a single phase section: intake-derived summary + any saved results."""
    if not phase_state:
        return ""
    # Pull query results out of _results bucket, render everything else as a kv table
    results = (phase_state.get("_results") or {})
    other = {k: v for k, v in phase_state.items() if k != "_results"}
    parts = [f"<section class='phase'><h2>{html.escape(phase_title)}</h2>"]
    if other:
        parts.append("<div class='summary'><h3>Summary fields</h3>")
        parts.append(_escape(other))
        parts.append("</div>")
    if results:
        parts.append("<div class='results'><h3>Query results</h3>")
        for key in sorted(results.keys()):
            parts.append(_render_result_block(results[key]))
        parts.append("</div>")
    parts.append("</section>")
    return "".join(parts)


PHASE_ORDER = [
    ("phase0", "Phase 0 — Triage"),
    ("phase1", "Phase 1 — Identity"),
    ("phase2", "Phase 2 — Verify"),
    ("phase3", "Phase 3 — Behaviour"),
    ("phase4", "Phase 4 — Controls"),
    ("phase5", "Phase 5 — Risk"),
    ("phase6", "Phase 6 — Reserves"),
    ("phase7", "Phase 7 — Peers"),
    ("phase8", "Phase 8 — Decision"),
    ("phase9", "Phase 9 — Handoff"),
]


def render_evidence_pack_html(
    case_id: str,
    applicant_name: str,
    state: dict,
    audit_log: list[dict] | None = None,
) -> str:
    """Return a complete branded HTML document for the evidence pack."""
    intake = state.get("intake", {}) or {}
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    legal_entity = intake.get("applicant_legal_entity") or ""
    regime = intake.get("regime_applied_for") or "—"
    case_officer = intake.get("case_officer") or "—"
    submission_date = intake.get("submission_date") or "—"
    decision = (state.get("phase8") or {})
    outcome = decision.get("outcome") or "Pending"
    reviewer = decision.get("second_reviewer") or "—"

    phase_sections = [
        _render_phase_section(key, title, state.get(key, {}) or {})
        for key, title in PHASE_ORDER
    ]
    phase_sections = [s for s in phase_sections if s]  # drop empties

    audit_html = ""
    if audit_log:
        audit_rows = "".join(
            f"<tr><td class='muted'>{html.escape(str(a.get('timestamp', '')))}</td>"
            f"<td>{html.escape(str(a.get('action', '')))}</td>"
            f"<td>{html.escape(str(a.get('detail') or ''))}</td></tr>"
            for a in audit_log
        )
        audit_html = (
            "<section class='audit'><h2>Audit log</h2>"
            f"<p class='note'>{len(audit_log)} recorded actions, most recent first.</p>"
            "<table class='data'><thead><tr>"
            "<th style='width:22%'>Timestamp</th><th style='width:22%'>Action</th><th>Detail</th>"
            f"</tr></thead><tbody>{audit_rows}</tbody></table></section>"
        )

    logo_uri = _embedded_logo_data_uri()
    logo_img = (
        f"<img src='{logo_uri}' alt='FCA' style='height:36px; width:auto;'/>"
        if logo_uri else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Evidence Pack — {html.escape(case_id)} — {html.escape(applicant_name)}</title>
<style>
  /* ---- Page setup ---- */
  @page {{
    size: A4;
    margin: 1.8cm 1.6cm 2cm 1.6cm;
    @bottom-right {{
      content: "Page " counter(page) " of " counter(pages);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 9pt; color: #888;
    }}
    @bottom-left {{
      content: "PROTOTYPE — internal use only";
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 9pt; color: {FCA_PURPLE};
    }}
  }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Source Sans Pro", sans-serif;
    margin: 0; padding: 0;
    color: #1c1c1c; line-height: 1.5;
  }}

  /* ---- Header bar ---- */
  .header {{
    background: linear-gradient(90deg, {FCA_PURPLE_DARK} 0%, {FCA_PURPLE} 100%);
    color: #ffffff;
    padding: 1.6rem 2rem;
    border-bottom: 4px solid {FCA_PURPLE_DARK};
  }}
  .header-row {{ display: flex; align-items: center; gap: 1.5rem; }}
  .header h1 {{
    color: #ffffff; margin: 0; font-size: 1.6rem; font-weight: 600;
    letter-spacing: 0.01em;
  }}
  .header .subtitle {{
    color: rgba(255,255,255,0.85); font-size: 0.9rem; margin-top: 0.3rem;
  }}

  /* ---- Prototype banner ---- */
  .banner-proto {{
    background: #fff4e6; color: #7a3f00; border-bottom: 1px solid #f5b042;
    padding: 0.55rem 2rem; font-size: 0.88rem; font-weight: 500;
  }}

  /* ---- Wrapper ---- */
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 0 2rem 2rem 2rem; }}

  /* ---- Case meta block ---- */
  .case-meta {{
    background: #faf6f8;
    border-left: 5px solid {FCA_PURPLE};
    padding: 1rem 1.3rem;
    margin: 1.5rem 0 2rem 0;
    border-radius: 3px;
    page-break-inside: avoid;
  }}
  .case-meta .meta-row {{
    display: grid; grid-template-columns: 180px 1fr; gap: 0.4rem 1rem;
    font-size: 0.95rem;
  }}
  .case-meta .meta-row .label {{
    color: {FCA_PURPLE}; font-weight: 600; text-transform: uppercase;
    font-size: 0.78rem; letter-spacing: 0.04em; align-self: center;
  }}

  /* ---- Sections ---- */
  h2 {{
    color: {FCA_PURPLE}; font-size: 1.25rem; font-weight: 600;
    margin-top: 2.4rem; margin-bottom: 0.6rem;
    padding-bottom: 0.4rem; border-bottom: 2px solid {FCA_PURPLE};
  }}
  h3 {{
    color: {FCA_PURPLE_DARK}; font-size: 1rem; font-weight: 600;
    margin-top: 1.4rem; margin-bottom: 0.5rem;
    border-left: 3px solid {FCA_PURPLE}; padding-left: 0.6rem;
  }}
  section.phase, section.audit, .case-meta, .result {{
    page-break-inside: avoid;
  }}

  /* ---- Tables ---- */
  table.kv, table.data {{ width: 100%; border-collapse: collapse; margin: 0.5rem 0 1rem 0; font-size: 0.9rem; }}
  table.kv th, table.kv td, table.data th, table.data td {{
    border: 1px solid #e3d3dc; padding: 0.45rem 0.65rem; vertical-align: top; text-align: left;
  }}
  table.kv th {{ background: #faf6f8; color: {FCA_PURPLE}; width: 30%; font-weight: 600; }}
  table.data thead th {{
    background: #faf6f8; color: {FCA_PURPLE}; font-weight: 600;
    border-bottom: 2px solid {FCA_PURPLE};
  }}
  table.data tbody tr:nth-child(even) {{ background: #fbfaff; }}
  table.data td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.data td.muted, .muted {{ color: #888; }}

  /* ---- Result blocks ---- */
  .result {{ margin: 0.6rem 0 1.4rem 0; }}
  .result-header {{
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 0.4rem 0.7rem; background: {FCA_PURPLE}; color: #fff;
    border-radius: 3px 3px 0 0;
  }}
  .result-label {{ font-weight: 600; font-size: 0.92rem; }}
  .result-meta  {{ font-size: 0.78rem; opacity: 0.85; font-family: monospace; }}
  .result table {{ margin-top: 0; border-radius: 0 0 3px 3px; }}
  .trunc {{ font-size: 0.8rem; color: #888; font-style: italic; margin: 0.2rem 0 0 0; }}
  .empty {{ padding: 0.6rem; background: #fafafa; border: 1px dashed #ddd; color: #888; }}
  .summary {{ margin-bottom: 1rem; }}

  /* ---- Footer ---- */
  .footer {{
    margin-top: 3rem; padding-top: 1rem; border-top: 2px solid {FCA_PURPLE};
    color: #666; font-size: 0.82rem;
  }}
  .footer strong {{ color: {FCA_PURPLE}; }}
</style>
</head>
<body>
  <div class="header">
    <div class="header-row">
      {logo_img}
      <div>
        <h1>UK FCA Firm Authorisation — Evidence Pack</h1>
        <div class="subtitle">Generated by the Firm Authorisation Workbench prototype</div>
      </div>
    </div>
  </div>

  <div class="banner-proto">
    ⚠️ <strong>Prototype output</strong> — generated by a Chainalysis-built workbench
    not endorsed by the FCA. Internal review and demonstration use only.
  </div>

  <div class="wrap">
    <div class="case-meta">
      <div class="meta-row">
        <div class="label">Case ID</div><div><code>{html.escape(case_id)}</code></div>
        <div class="label">Applicant (trading)</div><div>{html.escape(applicant_name)}</div>
        <div class="label">Legal entity</div><div>{html.escape(legal_entity) or "<em class='muted'>—</em>"}</div>
        <div class="label">Regime applied for</div><div>{html.escape(regime)}</div>
        <div class="label">Case officer</div><div>{html.escape(case_officer)}</div>
        <div class="label">Submission date</div><div>{html.escape(str(submission_date))}</div>
        <div class="label">Pack generated</div><div>{generated_at}</div>
        <div class="label">Decision (current)</div><div><strong>{html.escape(outcome)}</strong></div>
        <div class="label">Second reviewer</div><div>{html.escape(reviewer)}</div>
      </div>
    </div>

    <section class="intake">
      <h2>Application Intake</h2>
      {_escape(intake)}
    </section>

    {''.join(phase_sections)}

    {audit_html}

    <div class="footer">
      Generated by the <strong>UK Firm Authorisation Workbench</strong> Streamlit prototype
      (Chainalysis-built). Dashboard companion:
      <code>data.chainalysis.com/visualizations/dashboard/4015</code>.<br>
      Audit-trail integrity: every action that produced data on this page is recorded
      in the Audit log section. The pack reflects case state at the moment of generation.
    </div>
  </div>
</body>
</html>"""


def render_evidence_pack(
    case_id: str,
    applicant_name: str,
    state: dict,
    audit_log: list[dict] | None = None,
) -> tuple[bytes, str, str]:
    """Render the evidence pack.

    Returns ``(bytes, mime_type, suggested_filename)``. Tries WeasyPrint for
    PDF; falls back to HTML bytes when WeasyPrint isn't installed.
    """
    html_doc = render_evidence_pack_html(case_id, applicant_name, state, audit_log)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in case_id) or "case"
    try:
        from weasyprint import HTML  # type: ignore

        pdf_bytes = HTML(string=html_doc).write_pdf()
        return pdf_bytes, "application/pdf", f"evidence_{safe_id}_{stamp}.pdf"
    except Exception:
        return html_doc.encode("utf-8"), "text/html", f"evidence_{safe_id}_{stamp}.html"
