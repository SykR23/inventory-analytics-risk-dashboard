"""
Product identity reconciliation.

The item-naming convention changed in Sept 2024 (e.g.
  old:  HR1/AH/30013/H LINEN PRINT 12X16
  new:  30013/H LINEN PRINT 12X16 - 30013
) so the same physical product appears under two different names and looks like
two products. Both formats embed a 4–6 digit **style code** (the number before
the /F, /H, … fabric marker), which is unique per item, so we use that code as
the canonical product identity.

`reconcile(df)` collapses raw item rows to one row per (category, code, month),
summing quantities (which also merges new-era colour variants of the same
style), and replaces the display name with a clean, consistent label.
"""

from __future__ import annotations

import re

import pandas as pd

# 4–6 digit style code immediately before a single fabric letter (F, H, K, …)
# that is not part of a longer word (so "KN11/FO/9371/F" → 9371, not 11).
_CODE = re.compile(r"(\d{4,6})\s*/\s*[A-Za-z](?![A-Za-z])")
_SIZE = re.compile(r"(\d{1,3})\s*[xX]\s*(\d{1,3})")


def style_code(name: str) -> str | None:
    m = _CODE.search(str(name))
    return m.group(1) if m else None


def size_of(name: str) -> str | None:
    m = _SIZE.search(str(name))
    return f"{int(m.group(1))}X{int(m.group(2))}" if m else None


def _description(name: str) -> str:
    s = str(name)
    m = _CODE.search(s)
    if m:
        s = s[m.end():]
    s = re.sub(r"^\s*/\s*[A-Za-z]\b", " ", s)     # drop a leading /W width marker
    sz = _SIZE.search(s)
    if sz:
        s = s[:sz.start()]
    s = re.sub(r"\s*-\s*\d.*$", "", s)            # drop trailing " - 30013…"
    s = s.replace("*", " ")
    return re.sub(r"\s+", " ", s).strip(" -/").upper()


def product_key(name: str) -> str:
    """Canonical id: the style code, or the raw name (prefixed) when none found."""
    code = style_code(name)
    if code:
        return code
    return "~" + re.sub(r"\s+", " ", str(name).strip()).upper()


def product_label(name: str) -> str:
    code = style_code(name)
    if not code:
        return str(name).strip()
    parts = [code, _description(name), size_of(name) or ""]
    return " ".join(p for p in parts if p).strip()


def reconcile(df: pd.DataFrame):
    """
    Collapse raw items to one row per (category, product_key, month).

    Returns (reconciled_df, info) where info summarises the reconciliation for
    the data-health panel.
    """
    if df.empty:
        return df, {"enabled": True, "raw_items": 0, "products": 0,
                    "linked_across_rename": 0, "multi_size_codes": 0, "no_code_items": 0}

    d = df.copy()
    d["product_key"] = d["item"].map(product_key)
    d["product_label"] = d["item"].map(product_label)
    d["_code"] = d["item"].map(style_code)
    d["_size"] = d["item"].map(size_of)

    # one display label per key (the most common parsed label)
    labels = (d.groupby("product_key")["product_label"]
              .agg(lambda s: s.mode().iat[0] if not s.mode().empty else s.iat[0]))

    num = ["stock_available", "incoming", "outgoing", "stock_left"]
    keys = ["category", "product_key", "month", "month_date", "year", "month_num"]
    agg = d.groupby(keys, as_index=False)[num].sum()
    agg["item"] = agg["product_key"].map(labels)

    # --- stats for the health panel ---
    era = (d["month"] >= "2024-09")
    spanning = d.groupby("product_key").apply(
        lambda g: g.loc[era.loc[g.index]].shape[0] > 0 and g.loc[~era.loc[g.index]].shape[0] > 0,
        include_groups=False,
    )
    coded = d[d["_code"].notna()]
    multi_size = coded.groupby("_code")["_size"].nunique()
    info = {
        "enabled": True,
        "raw_items": int(d["item"].nunique()),
        "products": int(d["product_key"].nunique()),
        "linked_across_rename": int(spanning.sum()),
        "multi_size_codes": int((multi_size > 1).sum()),
        "no_code_items": int(d.loc[d["_code"].isna(), "item"].nunique()),
    }

    out = agg[["category", "item", "month", "month_date", "year", "month_num"] + num]
    out = out.sort_values(["category", "item", "month_date"]).reset_index(drop=True)
    return out, info
