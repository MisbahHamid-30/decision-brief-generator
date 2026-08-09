"""
Project audit
=============
Checks the repository is internally consistent and that a stranger can operate
it. Written after a review found the documentation drifting behind the code —
config paths that had moved, a file listing missing half the modules, a setup
guide addressed to someone who no longer existed.

Those defects were all found by hand, one at a time, by whoever happened to open
the file. That does not scale and does not repeat. This does.

Checks:
  A. Structure    every file the project needs is present
  B. References   every path named in docs or code exists
  C. Links        every relative markdown link resolves
  D. Commands     every command shown in docs names a real script
  E. Consistency  headline numbers in docs match the generated payload
  F. Hygiene      no placeholders, no private-session language, no stale paths
  G. Wiring       every profile resolves to a complete set of domain modules

    python3 src/audit_project.py
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results: list[tuple[str, str, bool, str]] = []


def check(family: str, name: str, passed: bool, detail: str = ""):
    results.append((family, name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT).replace("\\", "/")


def docs() -> list[str]:
    out = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in
                 {".git", "node_modules", "__pycache__", "samples"}]
        out += [os.path.join(dp, f) for f in fn if f.endswith(".md")]
    return sorted(out)


def code() -> list[str]:
    out = []
    for dp, dn, fn in os.walk(os.path.join(ROOT, "src")):
        dn[:] = [d for d in dn if d != "__pycache__"]
        out += [os.path.join(dp, f) for f in fn if f.endswith((".py", ".js"))]
    return sorted(out)


# ==========================================================================

def audit_structure():
    required = [
        "README.md", "RUNNING.md", "ARCHITECTURE.md", "PORTABILITY.md",
        "LICENSE", "requirements.txt", "package.json", ".gitignore",
        ".gitattributes", "skill/SKILL.md",
        "data/DATA_DICTIONARY.md", "data/DATA_DICTIONARY_RIDES.md",
        "data/samples/README.md", "docs/index.html",
        "src/ingest.py", "src/quality.py", "src/findings.py",
        "src/recommend.py", "src/recommend_rides.py",
        "src/run_analysis.py", "src/build_outputs.py", "src/make_samples.py",
        "src/generate_dummy_data.py", "src/generate_rides_data.py",
        "src/verify_signals.py", "src/verify_outputs.py", "src/verify_rides.py",
        "src/analysis/kpi_base.py", "src/analysis/kpi.py",
        "src/analysis/kpi_rides.py", "src/analysis/registry.py",
        "src/analysis/detectors.py", "src/analysis/detectors_rides.py",
        "src/render/theme.py", "src/render/charts.py",
        "src/render/charts_rides.py", "src/render/dashboard.py",
        "src/render/brief_docx.js", "src/render/deck_pptx.js",
    ]
    missing = [f for f in required if not os.path.exists(os.path.join(ROOT, f))]
    check("A", "all required files present", not missing,
          ", ".join(missing) if missing else f"{len(required)} files")


def audit_references():
    """Any repo-relative path mentioned in docs or code must exist."""
    pat = re.compile(r"`((?:src|config|data|docs|outputs|outputs_rides|skill)/[\w./<>*-]+)`")
    bad = []
    # Dated log entries in the working records are historical: they name paths
    # that were correct when written. Rewriting them to match today's layout
    # would falsify the record, so they are exempt from this check. Their
    # forward-looking sections are not — those are audited by hand and kept
    # current (see the "as built" structure in Project-Handoff.md).
    historical = {"Project-Handoff.md", "TASKS.md"}
    for f in [d for d in docs() if os.path.basename(d) not in historical] + code():
        try:
            text = open(f, encoding="utf-8").read()
        except Exception:
            continue
        is_source = f.endswith((".py", ".js"))
        for m in pat.findall(text):
            # <profile> and glob-ish placeholders are intentional
            if "<" in m or "*" in m:
                continue
            # Source naming a file it *writes* is documentation, not a broken
            # reference — generated outputs are git-ignored and legitimately
            # absent in a fresh clone. Docs linking to committed outputs are a
            # different matter and are covered by the link check.
            if is_source and m.startswith(("outputs/", "outputs_rides/",
                                           "data/careem_")):
                continue
            if not os.path.exists(os.path.join(ROOT, m)):
                bad.append(f"{rel(f)} → {m}")
    check("B", "every path named in docs and code exists", not bad,
          "; ".join(bad[:5]) if bad else "checked docs + source")


def audit_links():
    pat = re.compile(r"\]\(([^)#][^)]*)\)")
    bad = []
    for f in docs():
        base = os.path.dirname(f)
        for link in pat.findall(open(f, encoding="utf-8").read()):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target = os.path.normpath(os.path.join(base, link.split("#")[0]))
            if not os.path.exists(target):
                bad.append(f"{rel(f)} → {link}")
    check("C", "every relative markdown link resolves", not bad,
          "; ".join(bad[:5]) if bad else f"{len(docs())} files")


def audit_commands():
    pat = re.compile(r"python3?\s+(src[/\\][\w/\\]+\.py)")
    bad = set()
    for f in docs():
        for s in pat.findall(open(f, encoding="utf-8").read()):
            s = s.replace("\\", "/")
            if not os.path.exists(os.path.join(ROOT, s)):
                bad.add(s)
    check("D", "every documented command names a real script", not bad,
          ", ".join(sorted(bad)) if bad else "all resolve")


def audit_consistency():
    p = os.path.join(ROOT, "outputs", "brief_payload.json")
    if not os.path.exists(p):
        check("E", "headline numbers match the generated payload", False,
              "outputs/brief_payload.json missing — run build_outputs.py")
        return
    h = json.load(open(p))["headline"]
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()

    def k(v):
        return f"{round(v/1000):,.0f}k"

    want = {"net benefit": k(h["net_benefit"]),
            "investment": k(h["investment"]),
            "identified leak": k(h["total_leak"])}
    missing = [f"{name} (AED {v})" for name, v in want.items()
               if v not in readme]
    check("E", "README headline figures match the payload", not missing,
          "; ".join(missing) if missing
          else ", ".join(f"AED {v}" for v in want.values()))


PLACEHOLDERS = ["PASTE_DRIVE_LINK_HERE", "PASTE-YOURS-HERE", "YOUR-USERNAME",
                "YOUR-REAL-USERNAME", "TODO", "FIXME", "XXX"]
PRIVATE = ["in this chat", "ask me to run", "I run it in a", "paste this into a new chat"]


def audit_hygiene():
    public = [f for f in docs()
              if os.path.basename(f) not in
              {"Project-Handoff.md", "TASKS.md", "SUBMISSION.md"}]

    hits = []
    for f in public:
        t = open(f, encoding="utf-8").read()
        for ph in PLACEHOLDERS:
            if ph in t:
                hits.append(f"{rel(f)}: {ph}")
    check("F", "no unresolved placeholders in public docs", not hits,
          "; ".join(hits) if hits else f"{len(public)} files")

    hits = []
    for f in public:
        t = open(f, encoding="utf-8").read().lower()
        for ph in PRIVATE:
            if ph in t:
                hits.append(f"{rel(f)}: '{ph}'")
    check("F", "no private-session language in public docs", not hits,
          "; ".join(hits) if hits
          else "nothing addressed to a reader who cannot exist")

    stale = ["config/semantic_map.yaml", "config/business_rules.yaml",
             "data/dummy/"]
    hits = []
    for f in docs() + code():
        if os.path.basename(f) in {"Project-Handoff.md", "TASKS.md",
                                   "audit_project.py"}:
            continue
        t = open(f, encoding="utf-8").read()
        for s in stale:
            if s in t:
                hits.append(f"{rel(f)}: {s}")
    check("F", "no references to paths that have moved", not hits,
          "; ".join(hits) if hits else "config is per-profile everywhere")


def audit_wiring():
    """Each profile must have both config files, a data dictionary and a
    complete set of domain modules reachable through the registry."""
    cfg = os.path.join(ROOT, "config")
    profiles = sorted(d for d in os.listdir(cfg)
                      if os.path.isdir(os.path.join(cfg, d)))
    check("G", "at least two profiles ship", len(profiles) >= 2,
          ", ".join(profiles))

    bad = []
    for pr in profiles:
        for f in ("semantic_map.yaml", "business_rules.yaml"):
            if not os.path.exists(os.path.join(cfg, pr, f)):
                bad.append(f"{pr}/{f}")
    check("G", "every profile has both config files", not bad,
          ", ".join(bad) if bad else f"{len(profiles)} profiles")

    # every profile's declared domain must resolve through the registry
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import yaml
    bad = []
    for pr in profiles:
        sem = yaml.safe_load(open(os.path.join(cfg, pr, "semantic_map.yaml")))
        domain = sem["dataset"].get("domain", "supply_chain")
        try:
            from analysis import registry  # noqa
            src = open(os.path.join(ROOT, "src", "analysis",
                                    "registry.py"), encoding="utf-8").read()
            if domain != "supply_chain" and f'"{domain}"' not in src:
                bad.append(f"{pr}: domain '{domain}' not in registry")
        except Exception as e:
            bad.append(f"{pr}: {e}")
    check("G", "every profile's domain resolves in the registry", not bad,
          "; ".join(bad) if bad else "registry covers all declared domains")

    # both business_rules must define the config-driven blocks the base class
    # reads, otherwise the scorecard and waterfall silently come out empty
    bad = []
    for pr in profiles:
        rules = yaml.safe_load(open(os.path.join(cfg, pr, "business_rules.yaml")))
        for block in ("scorecard", "waterfall", "targets", "costs",
                      "quality_gate", "materiality", "recommendations"):
            if block not in rules:
                bad.append(f"{pr}: missing '{block}'")
    check("G", "every profile defines all config blocks the pipeline reads",
          not bad, "; ".join(bad) if bad else "7 blocks x each profile")


# ==========================================================================

def main() -> int:
    print("=" * 74)
    print("PROJECT AUDIT")
    print("=" * 74)
    print("\nA. Structure\n")
    audit_structure()
    print("\nB. References\n")
    audit_references()
    print("\nC. Links\n")
    audit_links()
    print("\nD. Commands\n")
    audit_commands()
    print("\nE. Consistency\n")
    audit_consistency()
    print("\nF. Hygiene\n")
    audit_hygiene()
    print("\nG. Wiring\n")
    audit_wiring()

    print("\n" + "=" * 74)
    passed = sum(1 for *_, ok, _ in results if ok)
    fams: dict[str, list[int]] = {}
    for fam, _, ok, _ in results:
        fams.setdefault(fam, [0, 0])
        fams[fam][1] += 1
        fams[fam][0] += int(ok)
    names = {"A": "Structure", "B": "References", "C": "Links", "D": "Commands",
             "E": "Consistency", "F": "Hygiene", "G": "Wiring"}
    for fam in sorted(fams):
        got, tot = fams[fam]
        print(f"  {fam}. {names[fam]:<13} {got}/{tot}")
    print(f"\n  TOTAL {passed}/{len(results)} checks passed")
    print("=" * 74)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
