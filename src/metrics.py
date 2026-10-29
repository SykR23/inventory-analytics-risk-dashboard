"""
Analytics for the Trends page.

Pure functions over the tidy table (one row per category/item/month):
  * monthly_totals      - store-wide units in/out/on-hand per month
  * seasonality         - average sales by calendar month + a year x month grid
  * abc_analysis        - Pareto ranking of products into A/B/C classes
  * turnover            - inventory turnover ratio per product
  * dead_stock          - items holding stock but with no recent sales

Nothing here knows about Streamlit, so the functions are easy to test.
"""

from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

MONTH_ABBR = {i: calendar.month_abbr[i] for i in range(1, 13)}


def monthly_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Store-wide totals per month."""
    out = (
        df.groupby("month_date", as_index=False)
        .agg(
            units_sold=("outgoing", "sum"),
            incoming=("incoming", "sum"),
            stock_available=("stock_available", "sum"),
        )
        .sort_values("month_date")
    )
    return out


def seasonality(df: pd.DataFrame):
    """
    Return (by_month, pivot):
      by_month - average store-wide units sold for each calendar month (Jan..Dec)
      pivot    - year x calendar-month grid of total units sold (for a heatmap)
    Computed on monthly store totals so it reflects the business, not item counts.
    """
    monthly = df.groupby(["year", "month_num"], as_index=False)["outgoing"].sum()

    by_month = (
        monthly.groupby("month_num", as_index=False)["outgoing"]
        .mean()
        .rename(columns={"outgoing": "avg_units_sold"})
    )
    by_month["month"] = by_month["month_num"].map(MONTH_ABBR)

    pivot = monthly.pivot(index="year", columns="month_num", values="outgoing")
    pivot = pivot.rename(columns=MONTH_ABBR)
    return by_month, pivot


def abc_analysis(df: pd.DataFrame, value_col: str = "outgoing") -> pd.DataFrame:
    """
    Pareto/ABC ranking of products by total units sold.
      A = products making up the top 80% of sales
      B = next 15%   |   C = final 5%
    """
    g = (
        df.groupby("item", as_index=False)[value_col]
        .sum()
        .rename(columns={value_col: "total"})
    )
    g = g[g["total"] > 0].sort_values("total", ascending=False).reset_index(drop=True)
    grand = g["total"].sum()
    if grand <= 0 or g.empty:
        g["pct"] = 0.0
        g["cum_pct"] = 0.0
        g["class"] = "C"
        g["rank"] = range(1, len(g) + 1)
        return g

    g["pct"] = g["total"] / grand * 100
    g["cum_pct"] = g["pct"].cumsum()
    g["class"] = np.where(g["cum_pct"] <= 80, "A",
                          np.where(g["cum_pct"] <= 95, "B", "C"))
    g["rank"] = range(1, len(g) + 1)
    return g


def turnover(df: pd.DataFrame) -> pd.DataFrame:
    """
    Inventory turnover per product = total units sold / average units on hand.
    Higher = sells through stock quickly; lower = capital tied up in slow stock.
    """
    g = (
        df.groupby("item", as_index=False)
        .agg(
            units_sold=("outgoing", "sum"),
            avg_stock=("stock_available", "mean"),
            months=("month", "nunique"),
        )
    )
    g["turnover"] = g["units_sold"] / g["avg_stock"].replace(0, np.nan)
    return g


def dead_stock(df: pd.DataFrame, window_months: int = 6) -> pd.DataFrame:
    """
    Items still holding stock but with zero sales over the last `window_months`.
    Uses each item's most recent record for the on-hand figure.
    """
    if df.empty:
        return df.assign(recent_sold=[], stock_left=[])

    last = df["month_date"].max()
    cutoff = last - pd.DateOffset(months=window_months - 1)
    recent = df[df["month_date"] >= cutoff]

    sold = (
        recent.groupby("item", as_index=False)["outgoing"]
        .sum()
        .rename(columns={"outgoing": "recent_sold"})
    )
    latest = (
        df.sort_values("month_date")
        .groupby("item", as_index=False)
        .tail(1)[["item", "month", "stock_left"]]
        .rename(columns={"month": "last_seen"})
    )
    merged = sold.merge(latest, on="item", how="left")
    dead = merged[(merged["recent_sold"] == 0) & (merged["stock_left"] > 0)]
    return dead.sort_values("stock_left", ascending=False).reset_index(drop=True)


# --- demand trend ----------------------------------------------------------

def yearly_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Long frame (year, month_num, month, units_sold) for a year-over-year overlay."""
    m = (
        df.groupby(["year", "month_num"], as_index=False)["outgoing"]
        .sum()
        .rename(columns={"outgoing": "units_sold"})
    )
    m["month"] = m["month_num"].map(MONTH_ABBR)
    return m


def monthly_with_anomalies(df: pd.DataFrame, z_thresh: float = 2.0) -> pd.DataFrame:
    """Monthly store totals with a z-score and an is_anomaly flag for outlier months."""
    t = monthly_totals(df).copy()
    s = t["units_sold"].astype(float)
    sd = s.std(ddof=0)
    t["z"] = (s - s.mean()) / sd if sd > 0 else 0.0
    t["is_anomaly"] = t["z"].abs() >= z_thresh
    return t


# --- flow & stockouts ------------------------------------------------------

def sell_through(df: pd.DataFrame) -> pd.DataFrame:
    """Store-wide sell-through % per month = Outgoing / (Available + Incoming)."""
    g = (
        df.groupby("month_date", as_index=False)
        .agg(
            outgoing=("outgoing", "sum"),
            available=("stock_available", "sum"),
            incoming=("incoming", "sum"),
        )
        .sort_values("month_date")
    )
    denom = (g["available"] + g["incoming"]).replace(0, np.nan)
    g["sell_through"] = g["outgoing"] / denom * 100
    return g


def stockouts(df: pd.DataFrame, top_n: int = 25):
    """
    Infer stockouts: a product that ended a month at zero stock while it was
    actually active (had sales or opening stock) likely lost potential sales.

    Returns (by_month, heat):
      by_month - count of stocked-out products per month
      heat     - top-N most-stocked-out products as an item x month 0/1 grid
    """
    d = df[["item", "month", "month_date", "stock_available", "outgoing", "stock_left"]].copy()
    d["stockout"] = (
        (d["stock_left"] <= 0) & ((d["outgoing"] > 0) | (d["stock_available"] > 0))
    ).astype(int)

    by_month = (
        d.groupby("month_date", as_index=False)["stockout"]
        .sum()
        .rename(columns={"stockout": "stockout_items"})
        .sort_values("month_date")
    )

    counts = d.groupby("item")["stockout"].sum()
    top_items = counts[counts > 0].sort_values(ascending=False).head(top_n).index.tolist()
    heat = (
        d[d["item"].isin(top_items)]
        .pivot_table(index="item", columns="month", values="stockout",
                     aggfunc="max", fill_value=0)
        .reindex(top_items)
    )
    return by_month, heat
