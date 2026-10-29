"""
Restock recommendations.

Combines forecasted demand (from src.forecast) with historical demand
variability and the store's lead time / service level to produce, per product:

  * safety stock      = z · σ_demand · √(lead + review)
  * reorder point     = demand·lead + z · σ_demand · √lead
  * order-up-to level = demand·(lead + review) + safety stock
  * recommended order = max(0, order-up-to − current stock on hand)
  * a status flag: Stockout risk / Reorder now / Overstock / OK

Monthly data, so the review period is 1 month. z comes from the service level
(e.g. 95% → 1.645) — the probability of not stocking out during lead time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.forecast import quick_forecast_table


def latest_stock(df: pd.DataFrame) -> pd.DataFrame:
    """Most recent on-hand (stock_left) per product."""
    latest = df.sort_values("month_date").groupby("item", as_index=False).tail(1)
    return latest[["item", "month", "stock_left"]].rename(
        columns={"stock_left": "on_hand", "month": "last_seen"})


def _demand_std(df: pd.DataFrame, items) -> pd.Series:
    """Historical month-to-month demand standard deviation per product."""
    d = df[df["item"].isin(items)]
    sd = d.groupby("item")["outgoing"].std().fillna(0.0)
    return sd


def restock_table(df: pd.DataFrame, lead_time_months: float = 1.0,
                  service_level: float = 0.95, overstock_cover: float = 6.0) -> pd.DataFrame:
    """Build the full per-product restock recommendation table."""
    if df.empty:
        return pd.DataFrame()

    L = max(0.0, float(lead_time_months))
    R = 1.0                       # monthly review period
    P = L + R                     # protection period
    z = float(norm.ppf(min(max(service_level, 0.5), 0.999)))
    n_lead = max(1, int(np.ceil(L)))

    fc = quick_forecast_table(df, horizon=max(3, n_lead))
    if fc.empty:
        return pd.DataFrame()

    month_cols = sorted(c for c in fc.columns if c not in ("item", "total"))
    fc = fc.set_index("item")
    avg_monthly_demand = fc[month_cols].mean(axis=1)        # forecast mean / month
    lead_demand = fc[month_cols[:n_lead]].sum(axis=1)       # demand over lead time

    items = fc.index
    on_hand = latest_stock(df).set_index("item")["on_hand"].reindex(items).fillna(0.0)
    sigma = _demand_std(df, items).reindex(items).fillna(0.0)

    t = pd.DataFrame(index=items)
    t["on_hand"] = on_hand
    t["avg_monthly_demand"] = avg_monthly_demand.round(1)
    t["demand_std"] = sigma.round(1)
    t["safety_stock"] = np.ceil(z * sigma * np.sqrt(P))
    t["reorder_point"] = np.ceil(avg_monthly_demand * L + z * sigma * np.sqrt(L))
    order_up_to = avg_monthly_demand * P + t["safety_stock"]
    t["recommended_order"] = np.ceil((order_up_to - on_hand).clip(lower=0))
    t["months_cover"] = np.where(avg_monthly_demand > 0,
                                 (on_hand / avg_monthly_demand).round(1), np.inf)

    cond_stockout = on_hand < lead_demand
    cond_reorder = on_hand <= t["reorder_point"]
    cond_overstock = (t["months_cover"] > overstock_cover) & (t["recommended_order"] <= 0)
    t["status"] = np.select(
        [cond_stockout, cond_reorder, cond_overstock],
        ["Stockout risk", "Reorder now", "Overstock"],
        default="OK",
    )

    severity = {"Stockout risk": 0, "Reorder now": 1, "OK": 2, "Overstock": 3}
    t["_sev"] = t["status"].map(severity)
    t = (t.reset_index()
           .sort_values(["_sev", "recommended_order"], ascending=[True, False])
           .drop(columns="_sev")
           .reset_index(drop=True))
    return t


def order_schedule(df: pd.DataFrame, lead_time_months: float = 1.0,
                   service_level: float = 0.95, horizon: int = 3) -> pd.DataFrame:
    """
    Forward order plan: how much to order each of the next `horizon` months.

    Simulates each product's inventory position forward under an order-up-to
    policy. In month t we top up to cover forecasted demand over the protection
    period (lead time + 1 review month) plus safety stock; orders placed in
    month t are assumed to arrive after the lead time. Returns a wide
    item x month table of recommended order quantities.
    """
    if df.empty:
        return pd.DataFrame()

    L = max(0, int(round(lead_time_months)))
    z = float(norm.ppf(min(max(service_level, 0.5), 0.999)))
    need_months = horizon + L

    fc = quick_forecast_table(df, horizon=max(need_months, 1))
    if fc.empty:
        return pd.DataFrame()

    month_cols = sorted(c for c in fc.columns if c not in ("item", "total"))
    fc = fc.set_index("item")
    items = fc.index
    F = fc[month_cols].to_numpy(dtype=float)          # (n_items, need_months)
    n, M = F.shape
    H = min(horizon, M)

    sigma = _demand_std(df, items).reindex(items).fillna(0.0).to_numpy()
    safety = np.ceil(z * sigma * np.sqrt(L + 1))
    on_hand = (latest_stock(df).set_index("item")["on_hand"]
               .reindex(items).fillna(0.0).to_numpy())

    inv_position = on_hand.astype(float).copy()
    orders = np.zeros((n, H))
    for ti in range(H):
        hi = min(ti + L + 1, M)
        protect = F[:, ti:hi].sum(axis=1)             # demand over protection period
        target = protect + safety                     # order-up-to level
        order = np.ceil(np.clip(target - inv_position, 0, None))
        orders[:, ti] = order
        inv_position = inv_position + order - F[:, ti]

    out = pd.DataFrame(orders, index=items, columns=month_cols[:H]).astype(int)
    out.insert(0, "on_hand", on_hand.astype(int))
    out["total_to_order"] = out[month_cols[:H]].sum(axis=1)
    return (out.reset_index()
               .sort_values("total_to_order", ascending=False)
               .reset_index(drop=True))
