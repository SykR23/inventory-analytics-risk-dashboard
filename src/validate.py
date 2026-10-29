"""
Data-health checks run against the combined tidy table.

These never stop the app; they surface problems in the Overview page so a user
who swaps in their own data can see, at a glance, whether it loaded cleanly.
"""

from __future__ import annotations

import pandas as pd

NUMERIC_COLUMNS = ["stock_available", "incoming", "outgoing", "stock_left"]


def validate(df: pd.DataFrame, tolerance: float = 0) -> dict:
    """Return a report dict summarising the health of the dataset."""
    report: dict = {
        "n_rows": int(len(df)),
        "n_items": int(df["item"].nunique()) if not df.empty else 0,
        "n_categories": int(df["category"].nunique()) if not df.empty else 0,
        "n_months": int(df["month"].nunique()) if not df.empty else 0,
        "date_min": None,
        "date_max": None,
        "negatives": {},
        "identity_violations": 0,
        "identity_sample": pd.DataFrame(),
        "timeline_gaps": 0,
        "gap_sample": pd.DataFrame(),
        "issues": [],
    }

    if df.empty:
        report["issues"].append(
            "No data was loaded. Check that files exist under "
            "data/<Category>/<Year>/<MonthName>.xlsx."
        )
        return report

    report["date_min"] = df["month"].min()
    report["date_max"] = df["month"].max()

    # Negative values (impossible for physical stock).
    negatives = {c: int((df[c] < 0).sum()) for c in NUMERIC_COLUMNS}
    report["negatives"] = {k: v for k, v in negatives.items() if v}
    if report["negatives"]:
        report["issues"].append(
            "Negative values found in: " + ", ".join(report["negatives"])
        )

    # Accounting identity: StockLeft = Available + Incoming - Outgoing.
    resid = (
        df["stock_available"] + df["incoming"] - df["outgoing"] - df["stock_left"]
    )
    viol_mask = resid.abs() > tolerance
    report["identity_violations"] = int(viol_mask.sum())
    if report["identity_violations"]:
        sample = df.loc[viol_mask, ["category", "item", "month"] + NUMERIC_COLUMNS].copy()
        sample["discrepancy"] = resid[viol_mask].astype(int)
        report["identity_sample"] = sample.head(50).reset_index(drop=True)
        report["issues"].append(
            f"{report['identity_violations']} row(s) where "
            "StockLeft ≠ Available + Incoming − Outgoing."
        )

    # Timeline gaps: months missing inside each item's active span. A changing
    # product roster is expected, so we only flag holes *between* an item's
    # first and last appearance, not before/after.
    gaps = _timeline_gaps(df)
    report["timeline_gaps"] = int(len(gaps))
    if not gaps.empty:
        report["gap_sample"] = gaps.head(50).reset_index(drop=True)
        report["issues"].append(
            f"{len(gaps)} missing month(s) inside the active span of some items."
        )

    return report


def _timeline_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Find (category, item, month) entries missing between first/last sighting."""
    rows = []
    for (cat, item), grp in df.groupby(["category", "item"]):
        months = pd.PeriodIndex(grp["month"], freq="M").sort_values()
        full = pd.period_range(months.min(), months.max(), freq="M")
        missing = full.difference(months)
        for p in missing:
            rows.append({"category": cat, "item": item, "missing_month": str(p)})
    return pd.DataFrame(rows)
