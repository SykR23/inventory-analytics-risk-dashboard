"""
Restock recommendations page.

Headline counts, a filterable per-product recommendation table (the "what to
order" list), a chart of the biggest orders, and a downloadable purchase list.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from scipy.stats import norm

from src.app_data import fmt_month, load_config, load_data
from src.restock import order_schedule, restock_table
from src.ui import apply_theme

st.set_page_config(page_title="Restock", page_icon="🛒", layout="wide")
apply_theme()
st.title("🛒 Restock Recommendations")

df, _files, _report = load_data()
cfg = load_config()
if df.empty:
    st.warning("No data loaded. Add your files and reload from the Overview page.")
    st.stop()

rcfg = cfg.get("restock", {})
with st.sidebar:
    st.header("Restock settings")
    lead = st.slider("Lead time (months)", 1, 6,
                     int(rcfg.get("lead_time_months", 1)))
    st.caption("Time from placing an order to stock arriving. Longer lead times "
               "raise reorder points and safety stock, so orders get bigger.")
    service = st.slider("Service level", 0.80, 0.99,
                        float(rcfg.get("service_level", 0.95)), step=0.01)
    st.caption("Target chance of NOT running out during the lead time. Higher "
               "means more safety stock and larger recommended orders.")
    overstock_cover = st.slider("Flag overstock above … months of cover", 3, 24, 6)
    st.caption("Products holding more than this many months of stock get the "
               "🔵 Overstock flag. Lower it to catch slow stock sooner.")
    plan_horizon = st.slider("Order-plan horizon (months)", 1, 12, 3)
    st.caption("How many upcoming months the order schedule below plans for.")

tbl = restock_table(df, lead_time_months=lead, service_level=service,
                    overstock_cover=overstock_cover)

if tbl.empty:
    st.info("No active products to generate recommendations for.")
    st.stop()

# --- headline counts -------------------------------------------------------
n_stockout = int((tbl["status"] == "Stockout risk").sum())
n_reorder = int((tbl["status"] == "Reorder now").sum())
n_over = int((tbl["status"] == "Overstock").sum())
to_order = tbl[tbl["recommended_order"] > 0]
units_to_order = int(to_order["recommended_order"].sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔴 Stockout risk", f"{n_stockout:,}",
          help="On hand won't cover demand during the lead time.")
c2.metric("🟠 Reorder now", f"{n_reorder:,}",
          help="At or below the reorder point.")
c3.metric("🔵 Overstock", f"{n_over:,}")
c4.metric("Units to order", f"{units_to_order:,}",
          help="Total recommended order quantity across all products.")

# --- biggest orders chart --------------------------------------------------
if not to_order.empty:
    st.subheader("Largest recommended orders")
    top = to_order.head(15).sort_values("recommended_order")
    fig = px.bar(top, x="recommended_order", y="item", orientation="h",
                 color="status",
                 color_discrete_map={"Stockout risk": "#d62728",
                                     "Reorder now": "#ff7f0e"})
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title="Units to order", yaxis_title="",
                      legend_title="")
    st.plotly_chart(fig, use_container_width=True)

# --- full table ------------------------------------------------------------
st.subheader("Recommendations")
statuses = ["Stockout risk", "Reorder now", "OK", "Overstock"]
chosen = st.multiselect("Filter by status", statuses,
                        default=["Stockout risk", "Reorder now"])
view = tbl[tbl["status"].isin(chosen)] if chosen else tbl
search = st.text_input("Search product")
if search:
    view = view[view["item"].str.contains(search, case=False, na=False)]

st.caption(f"Showing {len(view):,} of {len(tbl):,} products.")
st.dataframe(
    view[["item", "status", "on_hand", "avg_monthly_demand", "demand_std",
          "safety_stock", "reorder_point", "recommended_order", "months_cover"]],
    use_container_width=True, hide_index=True,
)

# --- purchase list download ------------------------------------------------
po = tbl[tbl["recommended_order"] > 0][
    ["item", "status", "on_hand", "avg_monthly_demand", "reorder_point", "recommended_order"]]
st.download_button(
    f"⬇️ Download purchase list ({len(po):,} products, {units_to_order:,} units)",
    po.to_csv(index=False).encode("utf-8"),
    file_name="purchase_list.csv",
    mime="text/csv",
)

# --- forward order schedule ------------------------------------------------
st.subheader(f"📅 Order schedule — next {plan_horizon} month(s)")
st.caption("How much to order each upcoming month, simulating stock forward "
           "from today's on-hand using the demand forecast and your lead time.")

sched = order_schedule(df, lead_time_months=lead, service_level=service,
                       horizon=plan_horizon)
if sched.empty:
    st.info("No active products to schedule orders for.")
else:
    month_cols = [c for c in sched.columns if c not in ("item", "on_hand", "total_to_order")]

    # store-wide buying calendar
    totals = sched[month_cols].sum().reset_index()
    totals.columns = ["month", "units"]
    totals["label"] = totals["month"].map(fmt_month)
    cfig = px.bar(totals, x="label", y="units", text="units",
                  category_orders={"label": [fmt_month(m) for m in month_cols]})
    cfig.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                       xaxis_title="", yaxis_title="Units to order")
    st.plotly_chart(cfig, use_container_width=True)

    sched_search = st.text_input("Search product", key="sched_search")
    sview = sched
    if sched_search:
        sview = sview[sview["item"].str.contains(sched_search, case=False, na=False)]
    sview = sview[["item", "on_hand"] + month_cols + ["total_to_order"]].rename(columns=fmt_month)
    st.dataframe(sview, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download order schedule (CSV)",
        sched.rename(columns=fmt_month).to_csv(index=False).encode("utf-8"),
        file_name="order_schedule.csv",
        mime="text/csv",
    )

# --- method explainer ------------------------------------------------------
with st.expander("How these numbers are calculated"):
    st.markdown(
        f"""
- **Lead time (L):** {lead} month(s) · **Review period:** 1 month · **Service level:** {service:.0%}
- **Safety stock** = z · σ_demand · √(L + 1), where z = {norm.ppf(service):.2f} for {service:.0%}
- **Reorder point** = demand · L + safety stock — when on-hand drops to this, reorder.
- **Order-up-to** = demand · (L + 1) + safety stock; **recommended order** = order-up-to − on-hand (never negative).
- **Demand** = the Phase-3 bulk forecast; **σ_demand** = historical month-to-month variability.

**Status:** 🔴 *Stockout risk* — on-hand won't survive the lead time · 🟠 *Reorder now* — at/below reorder point · 🔵 *Overstock* — more than {overstock_cover} months of cover · 🟢 *OK*.
        """
    )

st.divider()
st.caption("⚠️ Demand uses post-Sept-2024 product history (≤19 months) and an "
           "inferred lead time — tune **Lead time** and **Service level** in the "
           "sidebar to match your supplier reality.")
