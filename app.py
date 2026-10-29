"""
Streamlit entry point — Overview page.

Loads the data tree, runs health checks, and shows headline numbers plus a
sales-over-time teaser. Other pages (Trends, and later Forecast / Restock)
live in the pages/ folder and share the cached loader in src/app_data.py.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app_data import clear_cache, fmt_month, load_data
from src.ui import apply_theme

# ---------------------------------------------------------------------------

st.set_page_config(page_title="Inventory Analytics", page_icon="📦", layout="wide")
apply_theme()
st.title("📦 Inventory Analytics — Overview")

with st.sidebar:
    st.header("Data")
    st.caption(
        "Place your files as\n\n`data/<Category>/<Year>/<MonthName>.xlsx`\n\n"
        "then reload."
    )
    rescan = st.button("🔄 Re-scan data files")
    st.caption("Reloads your Excel files from disk. Click this after adding, "
               "removing, or editing data files so the dashboard picks up the changes.")
    if rescan:
        clear_cache()
        st.rerun()

df, files, report = load_data()

# --- empty-state guard -----------------------------------------------------
if df.empty:
    st.warning(
        "No data loaded yet. Add Excel files under "
        "`data/<Category>/<Year>/<MonthName>.xlsx` "
        "(or run `python scripts/make_sample_data.py` to generate a demo set), "
        "then click **Re-scan data files**."
    )
    if files:
        st.subheader("Files found")
        st.dataframe(pd.DataFrame(files), use_container_width=True)
    st.stop()

# --- headline KPIs ---------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Products", f"{report['n_items']:,}")
c2.metric("Categories", report["n_categories"])
c3.metric("Months", report["n_months"])
c4.metric("Date range", f"{fmt_month(report['date_min'])} → {fmt_month(report['date_max'])}")
c5.metric("Units sold (total)", f"{int(df['outgoing'].sum()):,}")

# --- sales-over-time teaser ------------------------------------------------
st.subheader("Units sold per month")
monthly = (
    df.groupby("month_date", as_index=False)["outgoing"].sum()
    .rename(columns={"outgoing": "units_sold"})
)
fig = px.line(monthly, x="month_date", y="units_sold", markers=True)
fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="Units sold")
st.plotly_chart(fig, use_container_width=True)

# --- data health -----------------------------------------------------------
st.subheader("Data health")
if not report["issues"]:
    st.success("All checks passed — data looks clean.")
else:
    for issue in report["issues"]:
        st.warning(issue)

with st.expander("Files loaded"):
    fdf = pd.DataFrame(files)
    st.dataframe(fdf, use_container_width=True)
    problems = fdf[fdf["status"] != "ok"] if not fdf.empty else fdf
    if not problems.empty:
        st.error("Some files were skipped or failed to read (see 'status'/'error').")

if report["identity_violations"]:
    with st.expander(f"Identity mismatches ({report['identity_violations']})"):
        st.caption("StockLeft should equal Available + Incoming − Outgoing.")
        sample = report["identity_sample"].copy()
        if "month" in sample.columns:
            sample["month"] = sample["month"].map(fmt_month)
        st.dataframe(sample, use_container_width=True)

if report["timeline_gaps"]:
    with st.expander(f"Timeline gaps ({report['timeline_gaps']})"):
        st.caption("Months missing inside an item's active span.")
        gaps = report["gap_sample"].copy()
        if "missing_month" in gaps.columns:
            gaps["missing_month"] = gaps["missing_month"].map(fmt_month)
        st.dataframe(gaps, use_container_width=True)

rec = report.get("reconcile", {})
if rec.get("enabled"):
    with st.expander("🔗 Product reconciliation (Sept-2024 rename)"):
        st.caption(
            "The item-naming format changed in Sept 2024, so the same physical "
            "product could appear under two names. Products are identified by "
            "their style code to link them across the change."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Products (reconciled)", f"{rec.get('products', 0):,}")
        c2.metric("Linked across the rename", f"{rec.get('linked_across_rename', 0):,}",
                  help="Products that existed in both naming formats and are now one product.")
        c3.metric("Items without a style code", f"{rec.get('no_code_items', 0):,}",
                  help="Kept under their original name (no 4–6 digit code found).")
        if rec.get("multi_size_codes"):
            st.caption(f"⚠️ {rec['multi_size_codes']} style codes appear with more "
                       "than one size; those sizes are merged under the code. "
                       "Set `products.reconcile: false` in config.yaml to disable.")

st.info("➡️ Open **Trends** in the left sidebar for seasonality, best-sellers, "
        "turnover, and dead-stock analysis, plus Forecast and Restock.")
