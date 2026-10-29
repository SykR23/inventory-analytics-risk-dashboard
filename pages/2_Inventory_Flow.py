"""
Inventory Flow & Stockouts page.

  1. Stock in vs out   - are we over- or under-ordering? + on-hand trend
  2. Sell-through rate  - what share of available stock actually sells
  3. Stockouts          - inferred lost-sales: products that hit zero stock
"""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.app_data import fmt_month, load_data, month_range_filter
from src.metrics import monthly_totals, sell_through, stockouts
from src.ui import LAVENDER, apply_theme

st.set_page_config(page_title="Inventory Flow", page_icon="🔁", layout="wide")
apply_theme()
st.title("🔁 Inventory Flow & Stockouts")

df_all, _files, _report = load_data()
if df_all.empty:
    st.warning("No data loaded. Add your files and reload from the Overview page.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    if df_all["category"].nunique() > 1:
        cats = sorted(df_all["category"].unique())
        chosen = st.multiselect("Categories", cats, default=cats)
        st.caption("Include only these product categories in the results below.")
        df_all = df_all[df_all["category"].isin(chosen)]
    df = month_range_filter(df_all)

# ===========================================================================
# 1. Stock in vs out
# ===========================================================================
st.header("1 · Stock in vs out")
st.caption("Incoming (up) vs units sold (down) each month, with total stock on "
           "hand. If the on-hand line keeps climbing, you're ordering faster "
           "than you sell.")
mt = monthly_totals(df)

total_in = int(mt["incoming"].sum())
total_out = int(mt["units_sold"].sum())
c1, c2, c3 = st.columns(3)
c1.metric("Total incoming", f"{total_in:,}")
c2.metric("Total sold", f"{total_out:,}")
c3.metric("Net stock change", f"{total_in - total_out:+,}",
          help="Incoming minus sold over the selected range.")

fig = go.Figure()
fig.add_bar(x=mt["month_date"], y=mt["incoming"], name="Incoming", marker_color="#2ca02c")
fig.add_bar(x=mt["month_date"], y=-mt["units_sold"], name="Sold", marker_color="#d62728")
fig.add_trace(go.Scatter(x=mt["month_date"], y=mt["stock_available"],
                         name="Stock on hand", mode="lines+markers",
                         line=dict(color=LAVENDER)))
fig.update_layout(barmode="relative", margin=dict(l=0, r=0, t=10, b=0),
                  xaxis_title="", yaxis_title="Units",
                  legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# 2. Sell-through rate
# ===========================================================================
st.header("2 · Sell-through rate")
st.caption("Units sold ÷ (stock available + incoming), per month. Rising toward "
           "100% suggests demand is outrunning supply — possible missed sales.")
stab = sell_through(df)
fig2 = px.line(stab, x="month_date", y="sell_through", markers=True)
fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                   xaxis_title="", yaxis_title="Sell-through %")
fig2.update_yaxes(ticksuffix="%")
st.plotly_chart(fig2, use_container_width=True)

# ===========================================================================
# 3. Stockouts (inferred lost sales)
# ===========================================================================
st.header("3 · Stockouts (inferred lost sales)")
st.caption("A product that ends a month at zero stock — while it was active — "
           "likely turned away sales. These aren't recorded, so we infer them.")
by_month, heat = stockouts(df, top_n=25)

fig3 = px.bar(by_month, x="month_date", y="stockout_items")
fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                   xaxis_title="", yaxis_title="Products stocked out")
st.plotly_chart(fig3, use_container_width=True)

st.subheader("Most frequently stocked-out products")
if heat.empty:
    st.success("No products hit zero stock in the selected range.")
else:
    heat = heat.rename(columns=fmt_month)
    hfig = px.imshow(heat, aspect="auto", color_continuous_scale="Reds",
                     labels=dict(color="Stocked out", x="Month", y="Product"))
    hfig.update_layout(margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
    st.plotly_chart(hfig, use_container_width=True)
    st.caption("Red = the product ended that month at zero stock.")

st.divider()
st.caption("⚠️ Stockouts here are *inferred* from zero end-of-month stock, not "
           "recorded lost sales — treat them as leads to investigate, not exact counts.")
