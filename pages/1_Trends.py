"""
Trends & best-sellers page.

Four sections, all respecting the sidebar month-range filter:
  1. Seasonality      - which months sell, averaged across years
  2. Best-sellers     - ABC/Pareto ranking of products
  3. Turnover         - fastest and slowest sellers relative to stock held
  4. Dead stock       - items holding stock with no recent sales
"""

from __future__ import annotations

import calendar

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.app_data import fmt_month, load_data, month_range_filter
from src.metrics import (
    abc_analysis,
    dead_stock,
    monthly_with_anomalies,
    seasonality,
    turnover,
    yearly_monthly,
)
from src.ui import LAVENDER, SEQUENTIAL, apply_theme

st.set_page_config(page_title="Trends", page_icon="📈", layout="wide")
apply_theme()
st.title("📈 Trends & Best-Sellers")

df_all, _files, _report = load_data()

if df_all.empty:
    st.warning("No data loaded. Add your files and reload from the Overview page.")
    st.stop()

# --- filters ---------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    if df_all["category"].nunique() > 1:
        cats = sorted(df_all["category"].unique())
        chosen = st.multiselect("Categories", cats, default=cats)
        st.caption("Include only these product categories in the results below.")
        df_all = df_all[df_all["category"].isin(chosen)]
    df = month_range_filter(df_all)

st.caption(
    f"Showing **{fmt_month(df['month'].min())} → {fmt_month(df['month'].max())}** · "
    f"{df['item'].nunique():,} products · {int(df['outgoing'].sum()):,} units sold."
)

# ===========================================================================
# 1. Seasonality
# ===========================================================================
st.header("1 · Sales trend & seasonality")

# Year-over-year overlay + anomaly-flagged monthly line
trend_l, trend_r = st.columns([1, 1])
with trend_l:
    st.subheader("Year-over-year")
    ym = yearly_monthly(df)
    month_order = [calendar.month_abbr[i] for i in range(1, 13)]
    yfig = px.line(ym, x="month", y="units_sold", color="year", markers=True,
                   category_orders={"month": month_order})
    yfig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                       xaxis_title="", yaxis_title="Units sold",
                       legend_title="Year")
    st.plotly_chart(yfig, use_container_width=True)
    st.caption("Each line is a year — compare growth and seasonal shape.")

with trend_r:
    st.subheader("Monthly trend & anomalies")
    anom = monthly_with_anomalies(df, z_thresh=2.0)
    afig = go.Figure()
    afig.add_trace(go.Scatter(x=anom["month_date"], y=anom["units_sold"],
                              mode="lines+markers", name="Units sold",
                              line=dict(color=LAVENDER)))
    flagged = anom[anom["is_anomaly"]]
    if not flagged.empty:
        afig.add_trace(go.Scatter(x=flagged["month_date"], y=flagged["units_sold"],
                                  mode="markers", name="Anomaly",
                                  marker=dict(color="#d62728", size=13,
                                              symbol="circle-open", line=dict(width=3))))
    afig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                       xaxis_title="", yaxis_title="Units sold",
                       legend=dict(orientation="h", y=1.15))
    st.plotly_chart(afig, use_container_width=True)
    n_flag = int(anom["is_anomaly"].sum())
    st.caption(f"Red rings = unusually high/low months (>2σ). {n_flag} flagged.")

st.subheader("Seasonality")
by_month, pivot = seasonality(df)

col_a, col_b = st.columns([1, 1])
with col_a:
    st.subheader("Average sales by calendar month")
    fig = px.bar(by_month, x="month", y="avg_units_sold")
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title="", yaxis_title="Avg units sold")
    st.plotly_chart(fig, use_container_width=True)
    peak = by_month.loc[by_month["avg_units_sold"].idxmax()]
    trough = by_month.loc[by_month["avg_units_sold"].idxmin()]
    st.caption(f"Strongest month on average: **{peak['month']}** · "
               f"weakest: **{trough['month']}**.")

with col_b:
    st.subheader("Year × month heatmap")
    if pivot.shape[0] >= 1:
        hfig = px.imshow(
            pivot, aspect="auto", color_continuous_scale=SEQUENTIAL,
            labels=dict(color="Units sold", x="Month", y="Year"),
        )
        hfig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(hfig, use_container_width=True)
    st.caption("Darker = more units sold. Blank cells = no data that month.")

# ===========================================================================
# 2. Best-sellers (ABC / Pareto)
# ===========================================================================
st.header("2 · Best-sellers (ABC / Pareto)")
abc = abc_analysis(df)

if abc.empty:
    st.info("No sales in the selected range.")
else:
    summary = (
        abc.groupby("class")
        .agg(products=("item", "size"), units=("total", "sum"))
        .reindex(["A", "B", "C"])
        .fillna(0)
    )
    summary["% of products"] = (summary["products"] / summary["products"].sum() * 100).round(1)
    summary["% of sales"] = (summary["units"] / summary["units"].sum() * 100).round(1)

    c1, c2, c3 = st.columns(3)
    for col, cls, desc in [(c1, "A", "top 80% of sales"),
                           (c2, "B", "next 15%"),
                           (c3, "C", "final 5%")]:
        n = int(summary.loc[cls, "products"])
        pct = summary.loc[cls, "% of products"]
        col.metric(f"Class {cls}", f"{n:,} products", f"{pct:.0f}% of range · {desc}")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Pareto curve")
        pfig = go.Figure()
        pfig.add_trace(go.Scatter(x=abc["rank"], y=abc["cum_pct"],
                                  mode="lines", name="Cumulative % of sales"))
        pfig.add_hline(y=80, line_dash="dot", annotation_text="80%")
        pfig.add_hline(y=95, line_dash="dot", annotation_text="95%")
        pfig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                           xaxis_title="Products (ranked by sales)",
                           yaxis_title="Cumulative % of units sold")
        st.plotly_chart(pfig, use_container_width=True)
    with right:
        st.subheader("Top sellers")
        top_n = st.slider("How many to show", 5, 50, 15, key="topn")
        top = abc.head(top_n)[["rank", "item", "total", "pct", "class"]].rename(
            columns={"total": "units_sold", "pct": "% of sales"})
        st.dataframe(top, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download full ABC ranking (CSV)",
        abc.to_csv(index=False).encode("utf-8"),
        file_name="abc_ranking.csv",
        mime="text/csv",
    )

# ===========================================================================
# 3. Inventory turnover
# ===========================================================================
st.header("3 · Inventory turnover")
st.caption("Turnover = units sold ÷ average units on hand. "
           "High = sells through quickly; low = capital tied up in slow stock.")
tov = turnover(df)
tov_valid = tov[(tov["avg_stock"] > 0) & (tov["units_sold"] > 0)].copy()
tov_valid["turnover"] = tov_valid["turnover"].round(2)
tov_valid["avg_stock"] = tov_valid["avg_stock"].round(1)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Fastest movers")
    st.dataframe(
        tov_valid.sort_values("turnover", ascending=False)
        .head(15)[["item", "units_sold", "avg_stock", "turnover"]],
        use_container_width=True, hide_index=True,
    )
with c2:
    st.subheader("Slowest movers (holding stock)")
    st.dataframe(
        tov_valid.sort_values("turnover", ascending=True)
        .head(15)[["item", "units_sold", "avg_stock", "turnover"]],
        use_container_width=True, hide_index=True,
    )

# ===========================================================================
# 4. Dead stock
# ===========================================================================
st.header("4 · Dead stock")
window = st.slider("No sales in the last N months", 1, 12, 6, key="deadwin")
dead = dead_stock(df, window_months=window)

if dead.empty:
    st.success(f"No dead stock: every product with stock on hand sold "
               f"at least once in the last {window} months.")
else:
    units = int(dead["stock_left"].sum())
    st.warning(f"**{len(dead):,} products** are holding stock "
               f"(**{units:,} units**) with no sales in the last {window} months.")
    dead_view = dead[["item", "last_seen", "stock_left", "recent_sold"]].copy()
    dead_view["last_seen"] = dead_view["last_seen"].map(fmt_month)
    st.dataframe(
        dead_view.rename(
            columns={"stock_left": "units_on_hand", "recent_sold": f"sold_last_{window}m"}),
        use_container_width=True, hide_index=True,
    )
    st.download_button(
        "⬇️ Download dead-stock list (CSV)",
        dead.to_csv(index=False).encode("utf-8"),
        file_name="dead_stock.csv",
        mime="text/csv",
    )

# --- caveat ----------------------------------------------------------------
st.divider()
st.caption(
    "⚠️ Note: product names changed format in Sept 2024, so a product sold in "
    "both periods may appear as two separate items in per-product lists "
    "(best-sellers, turnover, dead stock). Store-wide views (seasonality, totals) "
    "are unaffected. Reconciling the two naming schemes is a separate task."
)
