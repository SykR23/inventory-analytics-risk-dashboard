"""
Demand forecasting.

Per-product histories here are short and intermittent (and split by the Sept
2024 rename), so a single heavy model won't fit everything. Instead we keep a
ladder of methods and let a holdout backtest pick the best per series:

    moving_avg  -> seasonal_naive -> ses -> holt -> seasonal_hw

Everything operates on a clean monthly series (continuous month index, missing
months filled with 0 sales). Nothing here imports Streamlit.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

METHOD_NAMES = {
    "moving_avg": "Moving average (3 mo)",
    "seasonal_naive": "Seasonal naïve (last year)",
    "ses": "Simple exponential smoothing",
    "holt": "Holt (trend)",
    "seasonal_hw": "Holt-Winters (trend + seasonal)",
}


# --- series construction ---------------------------------------------------

def monthly_series(df: pd.DataFrame, item: str | None = None) -> pd.Series:
    """
    Monthly units-sold series with a continuous month index (gaps -> 0).
    item=None gives the store-wide total.
    """
    d = df if item is None else df[df["item"] == item]
    if d.empty:
        return pd.Series(dtype=float)
    s = d.groupby("month_date")["outgoing"].sum().sort_index()
    idx = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    s = s.reindex(idx, fill_value=0.0).astype(float)
    s.index.freq = "MS"
    return s


def _future_index(s: pd.Series, horizon: int) -> pd.DatetimeIndex:
    start = s.index[-1] + pd.DateOffset(months=1)
    return pd.date_range(start, periods=horizon, freq="MS")


# --- individual methods ----------------------------------------------------

def _candidate_methods(n: int) -> list[str]:
    methods = ["moving_avg"]
    if n >= 12:
        methods.append("seasonal_naive")
    if n >= 4:
        methods += ["ses", "holt"]
    if n >= 24:
        methods.append("seasonal_hw")
    return methods


def _forecast_method(method: str, s: pd.Series, h: int):
    """Return (forecast ndarray[h], fitted in-sample Series aligned to s.index)."""
    s = s.astype(float)
    if method == "moving_avg":
        val = float(s.tail(3).mean())
        fc = np.repeat(val, h)
        fitted = s.shift(1).rolling(3, min_periods=1).mean()
        return fc, fitted
    if method == "seasonal_naive":
        base = s.tail(12).values
        fc = np.array([base[i % len(base)] for i in range(h)], dtype=float)
        fitted = s.shift(12)
        return fc, fitted

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if method == "ses":
            res = SimpleExpSmoothing(s, initialization_method="estimated").fit()
        elif method == "holt":
            res = ExponentialSmoothing(
                s, trend="add", damped_trend=True,
                initialization_method="estimated").fit()
        elif method == "seasonal_hw":
            res = ExponentialSmoothing(
                s, trend="add", seasonal="add", seasonal_periods=12,
                initialization_method="estimated").fit()
        else:
            raise ValueError(f"unknown method: {method}")
        fc = np.asarray(res.forecast(h), dtype=float)
        fitted = res.fittedvalues
    return fc, fitted


def _safe_forecast(method: str, s: pd.Series, h: int):
    """_forecast_method with a moving-average fallback if a model blows up."""
    try:
        return _forecast_method(method, s, h)
    except Exception:
        return _forecast_method("moving_avg", s, h)


def _mae_mape(actual: np.ndarray, pred: np.ndarray):
    mae = float(np.mean(np.abs(pred - actual)))
    denom = np.where(actual == 0, np.nan, actual)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mape = float(np.nanmean(np.abs((pred - actual) / denom)) * 100)
    return mae, mape


# --- auto model selection + forecast ---------------------------------------

def auto_forecast(s: pd.Series, horizon: int, backtest_h: int = 6) -> dict:
    """
    Backtest the candidate methods on a holdout tail, pick the lowest-MAE one,
    refit on the full series, and forecast `horizon` months with a 95% band.
    """
    s = s.astype(float)
    n = len(s)
    bt = int(min(backtest_h, max(1, n // 4)))

    scores = []
    if n - bt >= 3:
        train, test = s.iloc[:-bt], s.iloc[-bt:]
        for m in _candidate_methods(len(train)):
            fc, _ = _safe_forecast(m, train, bt)
            mae, mape = _mae_mape(test.values, fc)
            scores.append({"method": m, "mae": mae, "mape": mape})

    if scores:
        best = min(scores, key=lambda r: r["mae"])["method"]
    else:
        best = "seasonal_naive" if n >= 12 else "moving_avg"

    fc, fitted = _safe_forecast(best, s, horizon)
    fc = np.clip(fc, 0, None)

    resid = (s - fitted).dropna()
    sd = float(resid.std(ddof=0)) if len(resid) > 1 else 0.0
    steps = np.arange(1, horizon + 1)
    band = 1.96 * sd * np.sqrt(steps)

    forecast = pd.DataFrame({
        "month_date": _future_index(s, horizon),
        "forecast": np.round(fc, 1),
        "lower": np.clip(fc - band, 0, None).round(1),
        "upper": (fc + band).round(1),
    })
    return {"method": best, "forecast": forecast, "fitted": fitted,
            "scores": scores, "n": n}


def holdout_backtest(s: pd.Series, bt: int = 6, method: str | None = None) -> dict:
    """
    Hold out the last `bt` months and forecast them, returning an
    actual-vs-predicted overlay plus accuracy. If `method` is given it is used
    directly (so it can match the forward forecast); otherwise auto-selected.
    """
    s = s.astype(float)
    if len(s) <= bt + 2:
        return {"overlay": pd.DataFrame(), "mae": np.nan, "mape": np.nan, "method": None}
    train, test = s.iloc[:-bt], s.iloc[-bt:]
    if method is None:
        res = auto_forecast(train, bt, backtest_h=min(6, max(1, len(train) // 4)))
        method = res["method"]
        pred = res["forecast"]["forecast"].values
    else:
        fc, _ = _safe_forecast(method, train, bt)
        pred = np.clip(fc, 0, None)
    mae, mape = _mae_mape(test.values, pred)
    overlay = pd.DataFrame({
        "month_date": test.index,
        "actual": test.values,
        "predicted": pred,
    })
    return {"overlay": overlay, "mae": mae, "mape": mape, "method": method}


# --- fast bulk forecast (feeds restock) ------------------------------------

def quick_forecast_table(df: pd.DataFrame, horizon: int = 3,
                         active_months: int = 6) -> pd.DataFrame:
    """
    Lightweight next-`horizon`-month forecast for every recently-active product.

    Uses a seasonal-naïve average (a product's mean sales in that calendar
    month historically), falling back to its recent average. Vectorised, so it
    runs instantly across thousands of products. Returns a wide item x month
    table. This is the quick baseline; the per-product view offers model choice.
    """
    if df.empty:
        return pd.DataFrame()

    last = df["month_date"].max()
    cutoff = last - pd.DateOffset(months=active_months - 1)
    recent = df[df["month_date"] >= cutoff]
    active = recent.groupby("item")["outgoing"].sum()
    active = active[active > 0].index
    d = df[df["item"].isin(active)]

    cal = d.groupby(["item", "month_num"])["outgoing"].mean()
    recent_avg = recent.groupby("item")["outgoing"].mean()

    rows = []
    for i in range(1, horizon + 1):
        fc_month = last + pd.DateOffset(months=i)
        mn = fc_month.month
        for item in active:
            val = cal.get((item, mn), np.nan)
            if pd.isna(val):
                val = recent_avg.get(item, 0.0)
            rows.append({"item": item,
                         "month": fc_month.strftime("%Y-%m"),
                         "forecast": max(0, round(float(val)))})

    long = pd.DataFrame(rows)
    wide = long.pivot(index="item", columns="month", values="forecast").fillna(0)
    wide["total"] = wide.sum(axis=1)
    return wide.sort_values("total", ascending=False).reset_index()
