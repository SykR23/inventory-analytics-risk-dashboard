"""
Ingestion layer.

Crawls a data tree laid out as::

    data/<Category>/<Year>/<MonthName>.xlsx

and turns the many monthly Excel files into a single tidy table with one row
per (category, item, month). Everything downstream consumes that table, so no
other module needs to know about folders or Excel.

Key realities this handles:
  * Partial years (e.g. 2026 may only have January..March).
  * A changing product roster (items appear / disappear month to month).
  * Loose column headers ("Stock available" vs "StockAvailable" vs ...).
  * Excel lock files (~$Name.xlsx) and stray non-data files, which are skipped.
  * Caching: the combined table is written to parquet and only rebuilt when the
    underlying files change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# --- month-name parsing ----------------------------------------------------

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


# --- column-header matching ------------------------------------------------
# Map each canonical column to the header spellings we accept. Synonyms are
# normalised (lowercased, stripped of spaces/punctuation) before matching, so
# "Stock available", "Stock Available" and "StockAvailable" all collapse to the
# same key.

CANONICAL_SYNONYMS = {
    "item": [
        "item", "itemname", "item name", "product", "productname",
        "product name", "name", "description", "sku", "style",
    ],
    "stock_available": [
        "stockavailable", "stock available", "availablestock", "available",
        "opening", "openingstock", "openingstk", "beginning", "stockavail",
    ],
    "incoming": [
        "incoming", "in", "received", "newstock", "stockin", "purchase",
        "purchases", "inward", "added", "restock",
    ],
    "outgoing": [
        "outgoing", "out", "sold", "sales", "unitssold", "soldunits",
        "stockout", "outward", "issued", "dispatched",
    ],
    "stock_left": [
        "stockleft", "stock left", "stockremaining", "stock remaining",
        "remainingstock", "remaining", "closing", "closingstock", "closingstk",
        "left", "balance", "ending", "endingstock",
    ],
}

REQUIRED_COLUMNS = ["item", "stock_available", "incoming", "outgoing", "stock_left"]
NUMERIC_COLUMNS = ["stock_available", "incoming", "outgoing", "stock_left"]


def _norm(text: str) -> str:
    """Lowercase and strip everything except letters/digits for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


_HEADER_LOOKUP = {
    _norm(syn): canon
    for canon, syns in CANONICAL_SYNONYMS.items()
    for syn in syns
}


def _to_number(s: pd.Series) -> pd.Series:
    """
    Coerce a quantity column to numbers, tolerating text such as "55 PCS",
    "-33 PCS", or "1,200 units". Pulls out the first signed number it finds;
    anything unparseable becomes 0.
    """
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0)
    cleaned = (
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(r"(-?\d+\.?\d*)")[0]
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)


def _map_columns(columns) -> dict:
    """Return {original_header: canonical_name} for headers we recognise."""
    mapping = {}
    for col in columns:
        canon = _HEADER_LOOKUP.get(_norm(col))
        if canon and canon not in mapping.values():
            mapping[col] = canon
    return mapping


# --- file discovery --------------------------------------------------------

@dataclass
class FileRecord:
    path: Path
    category: str
    year: int
    month: int
    status: str = "ok"          # "ok" | "skipped" | "error"
    error: str = ""
    n_rows: int = 0


@dataclass
class Manifest:
    files: list = field(default_factory=list)        # list[FileRecord]
    missing_columns: dict = field(default_factory=dict)  # path -> [missing]
    reconcile: dict = field(default_factory=dict)    # product-reconciliation stats

    @property
    def ok_files(self):
        return [f for f in self.files if f.status == "ok"]

    @property
    def problem_files(self):
        return [f for f in self.files if f.status != "ok"]


def _discover_files(data_dir: Path) -> list[FileRecord]:
    """Walk data/<Category>/<Year>/<MonthName>.xlsx and return file records."""
    records: list[FileRecord] = []
    if not data_dir.exists():
        return records

    for category_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        # Skip helper folders such as the processed-cache directory.
        if category_dir.name.startswith((".", "_")):
            continue
        category = category_dir.name

        for year_dir in sorted(p for p in category_dir.iterdir() if p.is_dir()):
            m = re.fullmatch(r"(\d{4})", year_dir.name.strip())
            if not m:
                continue
            year = int(m.group(1))

            for xls in sorted(year_dir.glob("*.xls*")):
                # Excel lock / temp files start with "~$".
                if xls.name.startswith("~$"):
                    continue
                month = MONTH_MAP.get(_norm(xls.stem))
                if month is None:
                    records.append(FileRecord(
                        path=xls, category=category, year=year, month=0,
                        status="skipped",
                        error=f"Could not read a month name from '{xls.stem}'.",
                    ))
                    continue
                records.append(FileRecord(xls, category, year, month))
    return records


# --- reading ---------------------------------------------------------------

def _read_one(rec: FileRecord) -> pd.DataFrame | None:
    """Read a single monthly file into canonical columns, or mark it errored."""
    try:
        # Read every sheet and concatenate (handles single- or multi-sheet files).
        sheets = pd.read_excel(rec.path, sheet_name=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surface any read failure to the UI
        rec.status = "error"
        rec.error = f"{type(exc).__name__}: {exc}"
        return None

    frames = []
    for sheet in sheets.values():
        if sheet.empty:
            continue
        mapping = _map_columns(sheet.columns)
        renamed = sheet.rename(columns=mapping)
        present = [c for c in REQUIRED_COLUMNS if c in renamed.columns]
        if "item" not in present:
            continue  # not a data sheet
        frames.append(renamed[present])

    if not frames:
        rec.status = "error"
        rec.error = "No sheet with the expected columns was found."
        return None

    df = pd.concat(frames, ignore_index=True)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        rec.status = "error"
        rec.error = f"Missing columns: {', '.join(missing)}."
        return None

    # Clean up.
    df["item"] = df["item"].astype(str).str.strip()
    df = df[df["item"].ne("") & df["item"].str.lower().ne("nan")]
    for col in NUMERIC_COLUMNS:
        df[col] = _to_number(df[col])

    df["category"] = rec.category
    df["year"] = rec.year
    df["month_num"] = rec.month
    df["month"] = f"{rec.year:04d}-{rec.month:02d}"

    rec.n_rows = len(df)
    return df


# --- caching ---------------------------------------------------------------

def _signature(records: list[FileRecord]) -> str:
    """A fingerprint of the input files so we can skip rebuilding when unchanged."""
    parts = []
    for r in records:
        try:
            st = r.path.stat()
            parts.append(f"{r.path}|{st.st_mtime_ns}|{st.st_size}")
        except OSError:
            parts.append(f"{r.path}|missing")
    return json.dumps(sorted(parts))


def build_dataset(config: dict, force: bool = False) -> tuple[pd.DataFrame, Manifest]:
    """
    Crawl the data tree and return (tidy_dataframe, manifest).

    The result is cached to parquet keyed on a fingerprint of the input files;
    pass force=True to rebuild unconditionally.
    """
    from src.paths import resolve
    data_dir = resolve(config.get("data_dir"), "data")
    processed_dir = resolve(config.get("processed_dir"), str(data_dir / "_processed"))
    processed_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = processed_dir / "inventory.parquet"
    sig_path = processed_dir / "inventory.signature.json"

    abs_negatives = bool(config.get("cleaning", {}).get("abs_negatives", False))
    reconcile_products = bool(config.get("products", {}).get("reconcile", True))

    records = _discover_files(data_dir)
    # Fold options into the cache key so toggling them rebuilds.
    signature = (_signature(records)
                 + f"|abs_negatives={abs_negatives}|reconcile={reconcile_products}")
    info_path = processed_dir / "reconcile.json"

    if not force and parquet_path.exists() and sig_path.exists():
        if sig_path.read_text(encoding="utf-8") == signature:
            df = pd.read_parquet(parquet_path)
            man = _rebuild_manifest_from_records(records, df)
            try:
                man.reconcile = json.loads(info_path.read_text(encoding="utf-8"))
            except Exception:
                pass
            return df, man

    frames = []
    for rec in records:
        if rec.status != "ok":
            continue
        df = _read_one(rec)
        if df is not None:
            frames.append(df)

    manifest = Manifest(files=records)

    if frames:
        data = pd.concat(frames, ignore_index=True)
        data["month_date"] = pd.to_datetime(data["month"] + "-01")
        data = data.sort_values(["category", "item", "month_date"]).reset_index(drop=True)
    else:
        data = pd.DataFrame(
            columns=["category", "item", "month", "month_date", "year", "month_num"]
            + NUMERIC_COLUMNS
        )

    # Apply cleaning rules (analysis data only; source files untouched).
    if abs_negatives and not data.empty:
        data[NUMERIC_COLUMNS] = data[NUMERIC_COLUMNS].abs()

    # Reconcile the Sept-2024 product rename: key products by their style code
    # so the same physical product is one product across both naming formats.
    if reconcile_products and not data.empty:
        from src.identity import reconcile
        data, manifest.reconcile = reconcile(data)
    else:
        manifest.reconcile = {"enabled": False}

    # Persist cache.
    try:
        data.to_parquet(parquet_path, index=False)
        sig_path.write_text(signature, encoding="utf-8")
        info_path.write_text(json.dumps(manifest.reconcile), encoding="utf-8")
    except Exception:  # noqa: BLE001 - caching is best-effort (e.g. missing pyarrow)
        pass

    return data, manifest


def _rebuild_manifest_from_records(records, df) -> Manifest:
    """When loading from cache, fill row counts from the cached frame."""
    counts = (
        df.groupby(["category", "year", "month_num"]).size().to_dict()
        if not df.empty else {}
    )
    for r in records:
        if r.status == "ok":
            r.n_rows = counts.get((r.category, r.year, r.month), 0)
    return Manifest(files=records)
