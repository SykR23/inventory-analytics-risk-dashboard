
"""Inventory Risk Analysis page.

An extension to the original Inventory Analytics Dashboard.
Summarizes historical stockout frequency and inventory exposure
using the existing synthetic inventory dataset.
"""

import plotly.express as px
import streamlit as st

from src.app_data import load_data, month_range_filter
from src.ui import apply_theme


st.set_page_config(
    page_title="Inventory Risk",
    page_icon="⚠️",
    layout="wide",
)

apply_theme()

st.title("⚠️ Inventory Risk Analysis")
st.caption(
    "Explore historical stockout frequency, product-level risk, "
    "and current recorded inventory across categories."
)

# ---------------------------------------------------------------------
# Load and filter data
# ---------------------------------------------------------------------

df_all, _files, _report = load_data()

if df_all.empty:
    st.warning("No inventory data is available.")
    st.stop()

with st.sidebar:
    st.header("Risk Analysis Filters")

    categories = sorted(
        df_all["category"].dropna().unique().tolist()
    )

    selected_categories = st.multiselect(
        "Categories",
        categories,
        default=categories,
    )

df = df_all[
    df_all["category"].isin(selected_categories)
].copy()

if df.empty:
    st.info("No data available for the selected categories.")
    st.stop()

df = month_range_filter(df, key="inventory_risk_range")

if df.empty:
    st.info("No data available for the selected month range.")
    st.stop()

# ---------------------------------------------------------------------
# Historical stockout identification
# Uses the same definition as src.metrics.stockouts().
# ---------------------------------------------------------------------

df["stockout"] = (
    (df["stock_left"] <= 0)
    & (
        (df["outgoing"] > 0)
        | (df["stock_available"] > 0)
    )
).astype(int)

# ---------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------

product_month_records = len(df)
stockout_records = int(df["stockout"].sum())

overall_stockout_rate = (
    100 * stockout_records / product_month_records
    if product_month_records
    else 0.0
)

latest_date = df["month_date"].max()

latest_records = (
    df[df["month_date"] == latest_date]
    .sort_values("month_date")
)

latest_stock_units = int(
    latest_records["stock_left"].clip(lower=0).sum()
)

st.subheader("Inventory risk overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Categories",
    f"{df['category'].nunique():,}",
)

col2.metric(
    "Products observed",
    f"{df['item'].nunique():,}",
)

col3.metric(
    "Stockout records",
    f"{stockout_records:,}",
)

col4.metric(
    "Historical stockout rate",
    f"{overall_stockout_rate:.2f}%",
)

st.caption(
    f"Latest recorded inventory date: {latest_date:%b %Y}. "
    "Stockout rate is calculated across observed product-month records."
)

# ---------------------------------------------------------------------
# Product-level risk ranking
# ---------------------------------------------------------------------

st.header("1. Products with the highest stockout frequency")

product_risk = (
    df.sort_values("month_date")
    .groupby("item", as_index=False)
    .agg(
        category=("category", "last"),
        stockout_records=("stockout", "sum"),
        product_month_records=("stockout", "size"),
        units_sold=("outgoing", "sum"),
        latest_stock=("stock_left", "last"),
    )
)

product_risk["stockout_rate_pct"] = (
    100
    * product_risk["stockout_records"]
    / product_risk["product_month_records"].replace(0, float("nan"))
).round(2)

product_risk = product_risk.sort_values(
    ["stockout_rate_pct", "stockout_records"],
    ascending=[False, False],
)

top_n = min(15, len(product_risk))

if product_risk.empty:
    st.info("No products are available for risk analysis.")
else:
    chart_data = (
        product_risk.head(top_n)
        .sort_values("stockout_rate_pct")
    )

    fig = px.bar(
        chart_data,
        x="stockout_rate_pct",
        y="item",
        orientation="h",
        color="stockout_rate_pct",
        hover_data=[
            "category",
            "stockout_records",
            "product_month_records",
            "units_sold",
            "latest_stock",
        ],
        labels={
            "item": "Product",
            "stockout_rate_pct": "Stockout records (%)",
            "category": "Category",
            "stockout_records": "Stockout records",
            "product_month_records": "Observed product-month records",
            "units_sold": "Units sold",
            "latest_stock": "Latest recorded stock",
        },
        title=f"Top {top_n} products by stockout frequency",
        color_continuous_scale="Purples",
    )

    fig.update_xaxes(rangemode="tozero")
    fig.update_layout(
        margin=dict(l=10, r=10, t=50, b=10),
        yaxis_title="",
        xaxis_title="Stockout records (% of observed months)",
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "A high historical stockout frequency warrants investigation, "
        "but does not prove lost sales. Products with limited history "
        "should be interpreted cautiously."
    )

# ---------------------------------------------------------------------
# Category-level summary
# ---------------------------------------------------------------------

st.header("2. Category-level operational summary")

category_summary = (
    df.groupby("category", as_index=False)
    .agg(
        products=("item", "nunique"),
        units_sold=("outgoing", "sum"),
        stockout_records=("stockout", "sum"),
        product_month_records=("item", "size"),
        average_stock_available=("stock_available", "mean"),
    )
)

category_summary["stockout_rate_pct"] = (
    100
    * category_summary["stockout_records"]
    / category_summary["product_month_records"].replace(0, float("nan"))
).round(2)

category_latest = (
    df.sort_values("month_date")
    .groupby(["category", "item"], as_index=False)
    .tail(1)
)

latest_by_category = (
    category_latest.groupby("category", as_index=False)
    .agg(
        latest_stock_units=("stock_left", "sum"),
    )
)

category_summary = category_summary.merge(
    latest_by_category,
    on="category",
    how="left",
)

category_summary["review_note"] = "Monitor inventory trends"

category_summary.loc[
    category_summary["stockout_rate_pct"] >= 20,
    "review_note",
] = "Review recurring stockouts"

category_summary.loc[
    (category_summary["stockout_rate_pct"] < 20)
    & (category_summary["latest_stock_units"] <= 0),
    "review_note",
] = "Review recorded stock availability"

st.dataframe(
    category_summary.sort_values(
        "stockout_rate_pct",
        ascending=False,
    ),
    use_container_width=True,
    hide_index=True,
)

st.caption(
    "The 20% review threshold is an illustrative rule, not a validated "
    "business standard. Review demand, incoming stock, and replenishment "
    "lead times before taking action."
)

# ---------------------------------------------------------------------
# Product-level inventory review
# ---------------------------------------------------------------------

st.header("3. Product inventory review")

st.caption(
    "Review products with recurring historical stockouts alongside "
    "their most recently recorded stock."
)

review = product_risk[
    [
        "item",
        "category",
        "stockout_records",
        "product_month_records",
        "stockout_rate_pct",
        "units_sold",
        "latest_stock",
    ]
].copy()

st.dataframe(
    review,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download inventory risk report (CSV)",
    data=review.to_csv(index=False).encode("utf-8"),
    file_name="inventory_risk_report.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------
# Interpretation and limitations
# ---------------------------------------------------------------------

st.divider()

st.subheader("How to interpret this report")

st.markdown(
    """
    - **Stockout frequency:** the proportion of observed product-month
      records that satisfy the project's historical stockout definition.
    - **Latest recorded stock:** stock reported in the latest available
      month for each product.
    - **Review notes:** simple screening rules to help prioritize
      further investigation, not automated purchasing instructions.
    """
)

st.warning(
    "This analysis uses synthetic inventory data from the existing "
    "project. It does not use Urban Company's internal data, measure "
    "service-provider availability, or directly estimate lost sales. "
    "The new page is an extension of an existing open-source project."
)
