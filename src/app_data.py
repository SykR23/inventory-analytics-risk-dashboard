"""
Shared, cached data access for all Streamlit pages.

Every page imports `load_data()` so the Excel tree is crawled and validated
once per session, not once per page. Filters live in the pages themselves.
"""

from __future__ import annotations

import calendar

import streamlit as st
import yaml

from src.ingest import build_dataset
from src.paths import base_dir
from src.validate import validate


def fmt_month(m) -> str:
    """Format an ISO 'YYYY-MM' month as a short label, e.g. 'Aug 2022'."""
    try:
        year, month = str(m).split("-")[:2]
        return f"{calendar.month_abbr[int(month)]} {year}"
    except (ValueError, IndexError, KeyError):
        return str(m)


@st.cache_data(show_spinner=False)
def load_config() -> dict:
    cfg_path = base_dir() / "config.yaml"
    if cfg_path.exists():
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return {}


@st.cache_data(show_spinner="Reading your Excel files…")
def load_data():
    """Return (df, files, report). Cached across pages and reruns."""
    cfg = load_config()
    df, manifest = build_dataset(cfg)
    tol = float(cfg.get("validation", {}).get("identity_tolerance", 0))
    report = validate(df, tolerance=tol)
    report["reconcile"] = manifest.reconcile
    files = [
        {
            "category": f.category, "year": f.year, "month": f.month,
            "status": f.status, "error": f.error, "n_rows": f.n_rows,
            "name": f.path.name,
        }
        for f in manifest.files
    ]
    return df, files, report


def clear_cache() -> None:
    load_data.clear()
    load_config.clear()


def month_range_filter(df, *, key: str = "range"):
    """
    Render a month range slider in the sidebar and return the filtered frame.
    No-op (returns df) when there are fewer than two months.
    """
    months = sorted(df["month"].unique())
    if len(months) < 2:
        return df
    lo, hi = st.select_slider(
        "Month range",
        options=months,
        value=(months[0], months[-1]),
        key=key,
        format_func=fmt_month,
    )
    st.caption("Limits every chart and table on this page to these months. "
               "Narrow it to focus on a season or a recent period.")
    return df[(df["month"] >= lo) & (df["month"] <= hi)]
