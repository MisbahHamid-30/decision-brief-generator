"""
The Finding object — the spine of the tool
==========================================
Every sentence that ends up in the brief is generated from a Finding, and every
Finding carries the evidence that produced it. Nothing is asserted that cannot
be traced back to a number, and every number knows which table it came from and
how much that table can be trusted.

This is the constraint that separates an analysis tool from a plausible-sounding
text generator. If a claim has no Finding behind it, it does not get written.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

# Finding categories map to who owns the fix.
CATEGORIES = {
    "service":     "Availability and fill rate",
    "waste":       "Shrink and expiry",
    "procurement": "Supplier performance and terms",
    "assortment":  "Range and slot productivity",
    "fleet":       "Last-mile capacity and cost",
    "demand":      "Demand pattern and forecasting",
    "network":     "Store and network performance",
    "quality":     "Data reliability",
}

DIRECTIONS = {"leak", "opportunity", "risk", "context"}


# ==========================================================================

@dataclass
class Evidence:
    """One verifiable number behind a claim."""
    label: str
    value: Any
    unit: str = ""
    comparator: str | None = None     # what it should be, or what peers do
    source: str = ""                  # table or method that produced it
    n: int | None = None              # sample size behind the number
    role: str = ""                    # "" | "rules_out"

    # `role="rules_out"` marks the evidence that eliminates the intuitive
    # explanation — the fill rate that shows a slow store is well stocked, the
    # correlation that shows supply ignores price. Renderers give it its own
    # panel. Identifying it by scanning the comparator text for "not" worked
    # until the wording changed, which is exactly the kind of coupling that
    # breaks silently.

    def render(self) -> str:
        v = self.value
        if isinstance(v, float):
            v = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
        s = f"{self.label}: {v}{(' ' + self.unit) if self.unit else ''}"
        if self.comparator:
            s += f" (vs {self.comparator})"
        if self.n:
            s += f" [n={self.n:,}]"
        return s

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    id: str
    headline: str                     # one sentence, decision-relevant
    category: str
    direction: str                    # leak | opportunity | risk | context
    entity_type: str                  # network | store | sku | supplier | category | daypart
    entities: list[str] = field(default_factory=list)

    magnitude_aed: float = 0.0        # annualised, signed positive
    magnitude_basis: str = ""         # exactly how that number was derived
    magnitude_low: float | None = None
    magnitude_high: float | None = None

    evidence: list[Evidence] = field(default_factory=list)
    method: str = ""                  # the analytical technique used
    confidence: float = 0.5
    confidence_basis: str = ""

    period: tuple[str, str] | None = None
    caused_by: list[str] = field(default_factory=list)   # upstream finding ids
    explains: list[str] = field(default_factory=list)    # downstream finding ids
    tags: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)           # supporting tables

    # ---- scoring ---------------------------------------------------------

    def score(self, rules: dict) -> float:
        """Rank findings by what deserves an executive's attention.

        materiality x confidence x actionability. A large number we are unsure
        about and a small number we are certain of should not automatically
        outrank each other — the product decides.
        """
        mat = rules["materiality"]
        floor = mat["min_annualised_impact_aed"]
        escalate = mat["escalation_impact_aed"]

        # log-scaled materiality so a 10x bigger leak is not 10x more important
        m = max(self.magnitude_aed, 0.0)
        materiality = math.log10(1 + m / max(floor, 1)) / math.log10(1 + escalate / max(floor, 1))
        materiality = min(materiality, 1.5)

        actionability = {
            "leak": 1.0, "risk": 0.85, "opportunity": 0.9, "context": 0.3,
        }.get(self.direction, 0.5)

        # A finding that explains other findings is a root cause and is worth
        # more than the symptoms it accounts for.
        root_bonus = 1.0 + 0.25 * len(self.explains)

        return materiality * self.confidence * actionability * root_bonus

    def is_material(self, rules: dict) -> bool:
        return self.magnitude_aed >= rules["materiality"]["min_annualised_impact_aed"]

    def evidence_lines(self) -> list[str]:
        return [e.render() for e in self.evidence]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [e.as_dict() for e in self.evidence]
        return d

    def __repr__(self) -> str:
        return (f"<Finding {self.id} {self.category}/{self.direction} "
                f"AED {self.magnitude_aed:,.0f} conf {self.confidence:.0%}>")


# ==========================================================================
# Confidence
# ==========================================================================

def statistical_confidence(p_value: float | None = None,
                           effect_size: float | None = None) -> float:
    """Map a test result to a 0-1 confidence.

    Deliberately conservative: a p-value alone never buys more than 0.95,
    because statistical significance on 700k rows is cheap and says nothing
    about whether the effect matters.
    """
    if p_value is None:
        return 0.7
    if p_value <= 0:
        c = 0.95
    else:
        c = min(0.95, max(0.4, 1 - p_value * 10))
    if effect_size is not None:
        # shrink confidence when the effect is trivially small
        c *= min(1.0, 0.5 + abs(effect_size))
    return float(min(c, 0.95))


def sample_confidence(n: int, n_adequate: int = 300) -> float:
    """Small samples are penalised; large ones plateau."""
    if n <= 0:
        return 0.0
    return float(min(1.0, 1 - math.exp(-n / max(n_adequate, 1))))


def combine_confidence(statistical: float, sample: float,
                       data_quality: float) -> float:
    """The weakest link dominates, but not absolutely.

    Geometric mean, so a single very weak component drags the result down
    without a single strong component being able to rescue it.
    """
    parts = [max(x, 0.01) for x in (statistical, sample, data_quality)]
    return float(round((parts[0] * parts[1] * parts[2]) ** (1 / 3), 3))


def describe_confidence(statistical: float, sample: float, dq: float,
                        n: int, method: str) -> str:
    return (f"{method}; statistical {statistical:.2f}, "
            f"sample {sample:.2f} (n={n:,}), data quality {dq:.2f}")


# ==========================================================================
# Collection
# ==========================================================================

class FindingSet:
    """Findings plus the operations the insight layer needs on them."""

    def __init__(self, findings: list[Finding] | None = None):
        self.findings: list[Finding] = findings or []

    def add(self, f: Finding | None):
        if f is not None:
            self.findings.append(f)

    def extend(self, fs: list[Finding]):
        for f in fs:
            self.add(f)

    def __len__(self):
        return len(self.findings)

    def __iter__(self):
        return iter(self.findings)

    def by_id(self, fid: str) -> Finding | None:
        return next((f for f in self.findings if f.id == fid), None)

    def link(self, cause_id: str, effect_id: str):
        """Record that one finding explains another."""
        cause, effect = self.by_id(cause_id), self.by_id(effect_id)
        if cause and effect:
            if effect_id not in cause.explains:
                cause.explains.append(effect_id)
            if cause_id not in effect.caused_by:
                effect.caused_by.append(cause_id)

    def material(self, rules: dict) -> list[Finding]:
        return [f for f in self.findings if f.is_material(rules)]

    def ranked(self, rules: dict) -> list[Finding]:
        return sorted(self.findings, key=lambda f: -f.score(rules))

    def roots(self, rules: dict) -> list[Finding]:
        """Findings that are not themselves explained by something upstream."""
        return [f for f in self.ranked(rules) if not f.caused_by]

    def total_leak_aed(self) -> float:
        """Sum of leaks, excluding any that are downstream of another leak —
        otherwise the same money is counted twice."""
        return sum(f.magnitude_aed for f in self.findings
                   if f.direction == "leak" and not f.caused_by)

    def as_list(self) -> list[dict]:
        return [f.as_dict() for f in self.findings]

    def summary_table(self, rules: dict):
        import pandas as pd
        rows = []
        for f in self.ranked(rules):
            rows.append({
                "id": f.id,
                "score": round(f.score(rules), 3),
                "category": f.category,
                "dir": f.direction,
                "AED/yr": round(f.magnitude_aed),
                "conf": f.confidence,
                "root": "yes" if not f.caused_by else "",
                "headline": f.headline[:88],
            })
        return pd.DataFrame(rows)
