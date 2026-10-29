"""
Demand Forecast page.

  1. Store-wide forecast - seasonal model + backtest accuracy + confidence band
  2. Per-product forecast - auto-selected model per chosen product
  3. Bulk next-N table    - quick forecast for every active product (feeds restock)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.app_data import fmt_month, load_config, load_data
from src.forecast import (
    METHOD_NAMES,
    auto_forecast,
    holdout_backtest,
    monthly_series,
    quick_forecast_table,
)
from src.ui import LAVENDER, PERIWINKLE, apply_theme

st.set_page_config(page_title="Forecast", page_icon="🔮", layout="wide")
apply_theme()
st.title("🔮 Demand Forecast")

df, _files, _report = load_data()
cfg = load_config()
if df.empty:
    st.warning("No data loaded. Add your files and reload from the Overview page.")
    st.stop()

with st.sidebar:
    st.header("Forecast settings")
    default_h = int(cfg.get("forecast", {}).get("horizon_months", 6))
    horizon = st.slider("Months to forecast", 1, 12, default_h)
    st.caption("How many months into the future to predict. Larger values look "
               "further ahead but are less certain — the confidence band widens.")
    bt_window = st.slider("Backtest window (months)", 3, 12, 6)
    st.caption("How many recent months are hidden from the model to test its "
               "accuracy (the MAE/MAPE figures). Larger = a tougher test on less "
               "training history.")


def forecast_chart(history: pd.Series, fc: pd.DataFrame, title_actual="Actual"):
    """History line + forecast line + shaded 95% band."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history.index, y=history.values, mode="lines",
                             name=title_actual, line=dict(color=PERIWINKLE)))
    # confidence band
    fig.add_trace(go.Scatter(x=fc["month_date"], y=fc["upper"], mode="lines",
                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fc["month_date"], y=fc["lower"], mode="lines",
                             line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(230,182,250,0.16)", name="95% range"))
    fig.add_trace(go.Scatter(x=fc["month_date"], y=fc["forecast"], mode="lines+markers",
                             name="Forecast", line=dict(color=LAVENDER, dash="dash")))
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="",
                      yaxis_title="Units sold", legend=dict(orientation="h", y=1.12))
    return fig


# ===========================================================================
# 1. Store-wide forecast
# ===========================================================================
st.header("1 · Store-wide demand forecast")
s = monthly_series(df)
res = auto_forecast(s, horizon, backtest_h=bt_window)
bt = holdout_backtest(s, bt_window, method=res["method"])

c1, c2, c3 = st.columns(3)
c1.metric("Model chosen", METHOD_NAMES.get(res["method"], res["method"]))
c2.metric("Backtest MAE", f"{bt['mae']:,.0f}" if pd.notna(bt["mae"]) else "—",
          help="Average error (units) on the held-out months. Lower is better.")
c3.metric("Backtest MAPE", f"{bt['mape']:.0f}%" if pd.notna(bt["mape"]) else "—",
          help="Average % error on the held-out months.")

st.plotly_chart(forecast_chart(s, res["forecast"]), use_container_width=True)

if pd.notna(bt["mape"]) and bt["mape"] > 40:
    st.info("📈 Monthly demand here is volatile, so percentage error is high and "
            "the confidence band is wide. Treat the forecast as **directional** "
            "(shape & scale), not exact.")

with st.expander("Backtest detail — accuracy of each candidate model"):
    if res["scores"]:
        sc = pd.DataFrame(res["scores"])
        sc["model"] = sc["method"].map(METHOD_NAMES)
        sc = sc[["model", "mae", "mape"]].round(1).sort_values("mae")
        st.dataframe(sc, use_container_width=True, hide_index=True)
    if not bt["overlay"].empty:
        ov = bt["overlay"].copy()
        ov["month"] = ov["month_date"].dt.strftime("%b %Y")
        st.caption("Held-out months — actual vs predicted:")
        st.dataframe(ov[["month", "actual", "predicted"]].round(0),
                     use_container_width=True, hide_index=True)

# ===========================================================================
# 2. Per-product forecast
# ===========================================================================
st.header("2 · Per-product forecast")
st.caption("Pick a product to forecast individually. The model is chosen "
           "automatically by backtest, based on how much history the product has.")

last = df["month_date"].max()
cutoff = last - pd.DateOffset(months=5)
active = (df[df["month_date"] >= cutoff].groupby("item")["outgoing"].sum())
active = active[active > 0].sort_values(ascending=False)

if active.empty:
    st.info("No products with recent sales to forecast.")
else:
    item = st.selectbox(
        f"Product ({len(active):,} with recent sales, busiest first)",
        active.index.tolist(),
    )
    si = monthly_series(df, item)
    ri = auto_forecast(si, horizon, backtest_h=bt_window)
    bi = holdout_backtest(si, bt_window, method=ri["method"])

    m1, m2, m3 = st.columns(3)
    m1.metric("History", f"{ri['n']} months")
    m2.metric("Model chosen", METHOD_NAMES.get(ri["method"], ri["method"]))
    m3.metric("Backtest MAE",
              f"{bi['mae']:,.1f}" if pd.notna(bi["mae"]) else "—")

    st.plotly_chart(forecast_chart(si, ri["forecast"]), use_container_width=True)

    fc_tab = ri["forecast"].copy()
    fc_tab["month"] = fc_tab["month_date"].dt.strftime("%b %Y")
    st.dataframe(fc_tab[["month", "forecast", "lower", "upper"]],
                 use_container_width=True, hide_index=True)

# ===========================================================================
# 3. Bulk forecast (feeds restock)
# ===========================================================================
st.header("3 · Bulk forecast — all active products")
st.caption("A fast seasonal-average forecast for every product sold in the last "
           "6 months. This is the baseline that will drive restock "
           "recommendations in the next phase.")

qt = quick_forecast_table(df, horizon=min(horizon, 6))
if qt.empty:
    st.info("No active products to forecast.")
else:
    st.write(f"**{len(qt):,} products** · forecast totals over the next "
             f"{min(horizon, 6)} month(s):")
    qt_disp = qt.rename(columns=fmt_month)
    st.dataframe(qt_disp, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download bulk forecast (CSV)",
        qt_disp.to_csv(index=False).encode("utf-8"),
        file_name="bulk_forecast.csv",
        mime="text/csv",
    )

st.divider()
st.caption("⚠️ Because product names changed in Sept 2024, per-product forecasts "
           "rely on history under the *current* naming only (≤19 months). "
           "Store-wide forecasts use the full history.")
