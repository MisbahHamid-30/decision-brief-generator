"""
Domain registry
===============
Maps the `domain` declared in a profile's semantic map to its KPI engine and
detector set. Adding a domain means adding an entry here and two files — not
editing any of the generic pipeline.
"""

from __future__ import annotations


def get_kpi_engine(ds, quality_report=None):
    domain = ds.semantic["dataset"].get("domain", "supply_chain")
    if domain == "rides":
        from .kpi_rides import RidesKPI
        return RidesKPI(ds, quality_report)
    from .kpi import KPIEngine
    return KPIEngine(ds, quality_report)


def get_detectors(ds):
    domain = ds.semantic["dataset"].get("domain", "supply_chain")
    if domain == "rides":
        from . import detectors_rides
        return detectors_rides
    from . import detectors
    return detectors


def run_detectors(ds, k, rules):
    return get_detectors(ds).run_all(ds, k, rules)


def get_charts(ds):
    """Chart module for the domain.

    The value waterfall and the action-value bar are reused unchanged across
    domains — both read config-driven structures. Everything else is as
    domain-specific as the detectors are.
    """
    domain = ds.semantic["dataset"].get("domain", "supply_chain")
    if domain == "rides":
        from render import charts_rides
        return charts_rides
    from render import charts
    return charts
