"""
Generate a realistic demo data tree so the app runs before you add real files.

Creates:  data/Shirts/<Year>/<MonthName>.xlsx  for 2022-01 .. 2026-03

The simulation includes seasonality, a changing product roster (items that
launch late or get discontinued), occasional restocks, and the odd stockout —
so every later analysis phase has something meaningful to show.

Run:  python scripts/make_sample_data.py
Delete the generated data/Shirts folder and drop in your own to go live.
"""

from __future__ import annotations

import calendar
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "Shirts"

START = pd.Period("2022-01", freq="M")
END = pd.Period("2026-03", freq="M")
N_PRODUCTS = 60          # keep the demo light; your real data can be 1000s
SEED = 7

COLORS = ["Blue", "Black", "White", "Red", "Green", "Grey", "Navy", "Olive"]
STYLES = ["Cotton Crew", "Linen Shirt", "Polo", "Oxford", "Flannel", "Henley", "V-Neck"]
SIZES = ["S", "M", "L", "XL"]


def build_products(rng: random.Random) -> list[dict]:
    products = []
    names = set()
    while len(products) < N_PRODUCTS:
        name = f"{rng.choice(COLORS)} {rng.choice(STYLES)} {rng.choice(SIZES)}"
        if name in names:
            continue
        names.add(name)
        # Most products live the whole span; some launch late or discontinue early.
        launch = START
        retire = END
        roll = rng.random()
        if roll < 0.15:
            launch = START + rng.randint(6, 30)
        elif roll < 0.30:
            retire = END - rng.randint(3, 24)
        products.append({
            "item": name,
            "base_demand": rng.randint(20, 220),
            "seasonal_amp": rng.uniform(0.1, 0.6),
            "peak_month": rng.choice([1, 6, 7, 12]),  # winter/summer peaks
            "launch": launch,
            "retire": retire,
        })
    return products


def demand_for(p: dict, period: pd.Period, rng: random.Random) -> int:
    seasonal = 1 + p["seasonal_amp"] * math.cos(
        2 * math.pi * (period.month - p["peak_month"]) / 12
    )
    noise = rng.uniform(0.8, 1.2)
    return max(0, int(round(p["base_demand"] * seasonal * noise)))


def main() -> None:
    rng = random.Random(SEED)
    np.random.seed(SEED)
    products = build_products(rng)

    periods = pd.period_range(START, END, freq="M")
    # Carry stock_left forward as next month's stock_available.
    carried = {p["item"]: 0 for p in products}

    for period in periods:
        rows = []
        for p in products:
            if period < p["launch"] or period > p["retire"]:
                carried[p["item"]] = 0
                continue

            available = carried[p["item"]]
            demand = demand_for(p, period, rng)

            # Restock when low or at launch: aim for ~2 months of cover.
            incoming = 0
            if period == p["launch"] or available < demand:
                target = int(demand * rng.uniform(1.8, 2.6))
                incoming = max(0, target - available)

            outgoing = min(demand, available + incoming)   # can't sell what you don't have
            left = available + incoming - outgoing
            carried[p["item"]] = left

            rows.append({
                "Item name": p["item"],
                "Stock available": available,
                "Incoming": incoming,
                "Outgoing": outgoing,
                "Stock Left": left,
            })

        year_dir = OUT_DIR / str(period.year)
        year_dir.mkdir(parents=True, exist_ok=True)
        month_name = calendar.month_name[period.month]   # "January", ...
        out_path = year_dir / f"{month_name}.xlsx"
        pd.DataFrame(rows).to_excel(out_path, index=False)

    print(f"Wrote demo data to {OUT_DIR}")
    print(f"  {len(products)} products across {len(periods)} months "
          f"({START} .. {END}).")


if __name__ == "__main__":
    main()
