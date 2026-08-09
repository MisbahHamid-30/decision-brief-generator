"""
Ingestion and semantic layer
============================
Loads a folder of CSV/Excel files, profiles every table, and exposes them
through a semantic vocabulary so that no downstream analysis code ever
references a raw column name.

Design rule: the analysis engine asks for a *concept* ("sold_units",
"revenue", "city") and the semantic layer resolves it to whatever table and
column happen to carry it. Repoint `config/semantic_map.yaml` at a different
dataset and the rest of the pipeline follows unchanged.

Usage
-----
    from ingest import Dataset
    ds = Dataset.load()
    inv = ds.enrich("inventory_daily")     # fact joined to its dimensions
    ds.profile_summary()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A "profile" is one domain: its data folder and its two config files share a
# name. Adding a domain means adding a folder, not editing code.
DEFAULT_PROFILE = "careem_quik"


def profile_paths(profile: str = DEFAULT_PROFILE) -> tuple[str, str, str]:
    """Return (data_dir, semantic_map, business_rules) for a profile."""
    cfg = os.path.join(ROOT, "config", profile)
    return (os.path.join(ROOT, "data", profile),
            os.path.join(cfg, "semantic_map.yaml"),
            os.path.join(cfg, "business_rules.yaml"))


DEFAULT_DATA, DEFAULT_SEMANTIC, DEFAULT_RULES = profile_paths()


# ==========================================================================
# Table profile
# ==========================================================================

@dataclass
class ColumnProfile:
    name: str
    dtype: str
    null_count: int
    null_pct: float
    n_unique: int
    sample: Any = None
    minimum: Any = None
    maximum: Any = None
    mean: float | None = None
    negative_count: int = 0

    def as_dict(self) -> dict:
        return {k: (v.item() if hasattr(v, "item") else v)
                for k, v in self.__dict__.items()}


@dataclass
class TableProfile:
    name: str
    file: str
    role: str
    n_rows: int
    n_cols: int
    memory_mb: float
    duplicate_rows: int
    primary_key: list[str] = field(default_factory=list)
    duplicate_pk: int = 0
    date_range: tuple[str, str] | None = None
    columns: list[ColumnProfile] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "columns"}
        d["columns"] = [c.as_dict() for c in self.columns]
        return d


def profile_table(df: pd.DataFrame, name: str, spec: dict) -> TableProfile:
    cols: list[ColumnProfile] = []
    for c in df.columns:
        s = df[c]
        cp = ColumnProfile(
            name=c,
            dtype=str(s.dtype),
            null_count=int(s.isna().sum()),
            null_pct=float(s.isna().mean()),
            n_unique=int(s.nunique(dropna=True)),
            sample=(None if s.dropna().empty
                    else _scalar(s.dropna().iloc[0])),
        )
        if pd.api.types.is_numeric_dtype(s):
            cp.minimum = _scalar(s.min())
            cp.maximum = _scalar(s.max())
            cp.mean = float(s.mean()) if len(s) else None
            cp.negative_count = int((s < 0).sum())
        elif pd.api.types.is_datetime64_any_dtype(s):
            cp.minimum = str(s.min())
            cp.maximum = str(s.max())
        cols.append(cp)

    pk = spec.get("primary_key", []) or spec.get("grain", []) or []
    pk = [k for k in pk if k in df.columns]
    dup_pk = int(df.duplicated(subset=pk).sum()) if pk else 0

    date_range = None
    dc = spec.get("date_column")
    if dc and dc in df.columns and pd.api.types.is_datetime64_any_dtype(df[dc]):
        date_range = (str(df[dc].min()), str(df[dc].max()))

    return TableProfile(
        name=name,
        file=spec.get("file", ""),
        role=spec.get("role", "unknown"),
        n_rows=len(df),
        n_cols=df.shape[1],
        memory_mb=round(df.memory_usage(deep=True).sum() / 1e6, 1),
        duplicate_rows=int(df.duplicated().sum()),
        primary_key=pk,
        duplicate_pk=dup_pk,
        date_range=date_range,
        columns=cols,
    )


def _scalar(v):
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return str(v)
    return v


# ==========================================================================
# Dataset
# ==========================================================================

class Dataset:
    """A loaded, profiled, semantically-mapped collection of tables."""

    def __init__(self, tables: dict[str, pd.DataFrame], semantic: dict,
                 rules: dict, profiles: dict[str, TableProfile],
                 data_dir: str):
        self.tables = tables
        self.semantic = semantic
        self.rules = rules
        self.profiles = profiles
        self.data_dir = data_dir
        self._enriched: dict[str, pd.DataFrame] = {}

    # ---- loading ---------------------------------------------------------

    @classmethod
    def load(cls, data_dir: str | None = None,
             semantic_path: str | None = None,
             rules_path: str | None = None,
             verbose: bool = True,
             profile: str = DEFAULT_PROFILE) -> "Dataset":
        d, s, r = profile_paths(profile)
        data_dir = data_dir or d
        semantic_path = semantic_path or s
        rules_path = rules_path or r

        with open(semantic_path) as f:
            semantic = yaml.safe_load(f)
        with open(rules_path) as f:
            rules = yaml.safe_load(f)

        tables: dict[str, pd.DataFrame] = {}
        profiles: dict[str, TableProfile] = {}
        missing: list[str] = []

        for name, spec in semantic["tables"].items():
            path = os.path.join(data_dir, spec["file"])
            if not os.path.exists(path):
                missing.append(spec["file"])
                if verbose:
                    print(f"  ! missing: {spec['file']}")
                continue
            df = cls._read(path)
            df = cls._coerce_dates(df, spec, name, semantic)
            df = cls._compact(df, spec)
            tables[name] = df
            profiles[name] = profile_table(df, name, spec)
            if verbose:
                print(f"  loaded {name:18s} {len(df):>9,} rows x {df.shape[1]:>2} cols"
                      f"  ({profiles[name].memory_mb:>6.1f} MB)")

        # Fail here, with the fix, rather than several layers downstream with a
        # KeyError naming a table the reader has never heard of. The datasets
        # are not committed — they are large and reproducible — so a fresh
        # clone hits this first, and the message has to say so.
        if missing:
            gen = {"careem_quik": "src/generate_dummy_data.py",
                   "careem_rides": "src/generate_rides_data.py"}
            script = gen.get(os.path.basename(data_dir.rstrip("/\\")),
                             "the generator for this profile")
            raise FileNotFoundError(
                f"\n\n  {len(missing)} data file(s) not found in {data_dir}\n"
                f"    missing: {', '.join(missing)}\n\n"
                f"  The datasets are not committed to the repository — they are "
                f"~174 MB and\n  fully reproducible. Generate this one with:\n\n"
                f"      python {script}\n\n"
                f"  Or download it from the Drive link in README.md and unpack "
                f"it into\n  {data_dir}\n")

        return cls(tables, semantic, rules, profiles, data_dir)

    @staticmethod
    def _read(path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".csv", ".txt"):
            return pd.read_csv(path, low_memory=False)
        if ext in (".xlsx", ".xls", ".xlsm"):
            return pd.read_excel(path)
        if ext == ".parquet":
            return pd.read_parquet(path)
        raise ValueError(f"unsupported file type: {path}")

    @staticmethod
    def _coerce_dates(df: pd.DataFrame, spec: dict, table: str,
                      semantic: dict) -> pd.DataFrame:
        """Parse date columns, declared ones first.

        An earlier version guessed purely from column-name suffixes
        (`*_date`, `*_datetime`). That silently failed on a second dataset
        whose timestamps were called `requested_at` and `week_start` — the
        columns loaded as strings and the analysis fell over downstream with
        an error that pointed nowhere near the cause.

        The declared sources are authoritative: the table's `date_column` and
        any concept mapped to this table with a date-like `kind`. The name
        heuristic stays, but only as a fallback for columns nobody declared.
        """
        declared: set[str] = set()
        if spec.get("date_column"):
            declared.add(spec["date_column"])
        for c in semantic.get("concepts", {}).values():
            if c.get("table") == table and c.get("kind") in ("date", "datetime"):
                declared.add(c["column"])
        for key in spec.get("grain", []) or []:
            if key.lower() in ("date", "datetime", "timestamp"):
                declared.add(key)

        for c in df.columns:
            if c not in declared and df[c].dtype != object:
                continue
            lc = c.lower()
            looks_like_date = (lc.endswith("_date") or lc.endswith("_datetime")
                               or lc.endswith("_at") or lc.startswith("week_")
                               or lc in ("date", "datetime", "timestamp"))
            if c in declared or looks_like_date:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        return df

    @staticmethod
    def _compact(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
        """Downcast to keep large fact tables in memory comfortably."""
        for c in df.columns:
            s = df[c]
            if s.dtype == object and 0 < s.nunique(dropna=True) <= max(64, len(s) * 0.01):
                df[c] = s.astype("category")
            elif pd.api.types.is_integer_dtype(s):
                df[c] = pd.to_numeric(s, downcast="integer")
            elif pd.api.types.is_float_dtype(s):
                df[c] = pd.to_numeric(s, downcast="float")
        return df

    # ---- semantic access -------------------------------------------------

    def concept(self, name: str) -> tuple[str, str]:
        """Resolve a concept to (table, column). Raises if unmapped."""
        c = self.semantic["concepts"].get(name)
        if c is None:
            raise KeyError(f"concept '{name}' is not defined in the semantic map")
        return c["table"], c["column"]

    def has(self, name: str) -> bool:
        return name in self.semantic["concepts"]

    def col(self, name: str) -> str:
        """Column name for a concept."""
        return self.concept(name)[1]

    def table(self, name: str) -> pd.DataFrame:
        if name not in self.tables:
            raise KeyError(f"table '{name}' was not loaded")
        return self.tables[name]

    def spec(self, name: str) -> dict:
        return self.semantic["tables"][name]

    @property
    def currency(self) -> str:
        return self.semantic["dataset"].get("currency", "AED")

    @property
    def is_synthetic(self) -> bool:
        return bool(self.semantic["dataset"].get("synthetic", False))

    def to_usd(self, aed: float) -> float:
        return aed / self.semantic["dataset"]["fx"]["USD"]

    # ---- joins -----------------------------------------------------------

    def enrich(self, fact: str, drop_keys: bool = False) -> pd.DataFrame:
        """Left-join a fact table to every dimension it points at.

        Cached, because the fact tables are large and several analyzers want
        the same enriched frame.
        """
        if fact in self._enriched:
            return self._enriched[fact]

        df = self.table(fact).copy()
        fks = self.spec(fact).get("foreign_keys", {}) or {}
        for local_col, ref in fks.items():
            ref_table, ref_col = ref.split(".")
            if ref_table not in self.tables:
                continue
            dim = self.tables[ref_table]
            # only bring across columns we do not already have
            bring = [c for c in dim.columns if c not in df.columns or c == ref_col]
            if ref_col not in bring:
                bring.append(ref_col)
            right = dim[bring].drop_duplicates(subset=[ref_col])
            df = df.merge(right, how="left", left_on=local_col, right_on=ref_col)
            if drop_keys and ref_col != local_col and ref_col in df.columns:
                df = df.drop(columns=[ref_col])

        self._enriched[fact] = df
        return df

    def add_derived(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attach the derived measures declared in the semantic map, where the
        inputs are present in this frame."""
        def c(concept):
            try:
                return self.col(concept)
            except KeyError:
                return None

        sold, price, cost = c("sold_units"), c("unit_price"), c("unit_cost")
        waste, lost = c("waste_units"), c("lost_demand_units")
        recv = c("received_units")

        if sold in df and price in df:
            df["revenue_aed"] = df[sold] * df[price]
        if sold in df and cost in df:
            df["cogs_aed"] = df[sold] * df[cost]
        if "revenue_aed" in df and "cogs_aed" in df:
            df["gross_margin_aed"] = df["revenue_aed"] - df["cogs_aed"]
        if waste in df and cost in df:
            df["waste_cost_aed"] = df[waste] * df[cost]
        if lost in df and price in df:
            df["lost_revenue_aed"] = df[lost] * df[price]
        if lost in df and price in df and cost in df:
            df["lost_margin_aed"] = df[lost] * (df[price] - df[cost])
        if recv in df:
            df["received_units_"] = df[recv]
        return df

    # ---- reporting -------------------------------------------------------

    def profile_summary(self) -> pd.DataFrame:
        rows = []
        for name, p in self.profiles.items():
            rows.append({
                "table": name,
                "role": p.role,
                "rows": p.n_rows,
                "cols": p.n_cols,
                "MB": p.memory_mb,
                "dup_rows": p.duplicate_rows,
                "dup_pk": p.duplicate_pk,
                "date_from": p.date_range[0][:10] if p.date_range else "",
                "date_to": p.date_range[1][:10] if p.date_range else "",
            })
        return pd.DataFrame(rows)

    def as_dict(self) -> dict:
        return {
            "dataset": self.semantic["dataset"],
            "data_dir": self.data_dir,
            "tables": {k: v.as_dict() for k, v in self.profiles.items()},
        }


if __name__ == "__main__":
    print("Loading dataset ...")
    ds = Dataset.load()
    print()
    print(ds.profile_summary().to_string(index=False))
    print(f"\ncurrency={ds.currency}  synthetic={ds.is_synthetic}")
    print(f"concepts mapped: {len(ds.semantic['concepts'])}")
