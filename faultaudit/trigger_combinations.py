"""Deterministic case/mode sets and same-scenario intersections, never causality."""
from __future__ import annotations

from itertools import combinations

from .store import AuditError

POSITIVE = {"APPLICABLE", "PARTIAL"}


def _current(data):
    values = {}
    for a in data.get("assessments", []):
        if not a.get("is_stale"):
            values[a["assessment_id"]] = a
    return list(values.values())


def analyze(data):
    """Keep frame versions, evidence axes and counting units independent."""
    subjects = {s["case_id"]: s for s in data.get("subjects", [])}
    init = data.get("phase") == "INIT"
    unit_for = {cid: (s.get("mode_id") or cid) if init else cid for cid, s in subjects.items()}
    units = sorted(set(unit_for.values()))
    assessments = _current(data)
    tax = data.get("taxonomy", {})
    api_scheme = data.get("input_condition_scheme", "ORIGINAL42")
    if api_scheme != "ORIGINAL42":
        raise AuditError("Archived input scheme cannot enter original-rule combination reports")
    frames = [(api_scheme, tax.get("definition_version") or tax.get("taxonomy_hash") or tax.get("taxonomy_id") or "UNVERSIONED", tax.get("items", []), "rows")]
    if data.get("v4_taxonomy"):
        v4 = data["v4_taxonomy"]
        frames.insert(0, ("V4", v4["definition_version"], v4["items"], "v4_rows"))
    output = []
    for scheme, version, definitions, field in frames:
        for axis in ("DESCRIPTION", "EVIDENCE_CONFIRMED"):
            by_unit = {u: set() for u in units}
            scenario_sets = {}
            assessed = set()
            legacy_without_scenarios = set()
            for a in assessments:
                if a.get("baseline_axis") and a["baseline_axis"] != ("V4" if scheme == "V4" else "API42"):
                    continue
                cid = a["case_id"]
                if cid not in unit_for:
                    continue
                u = unit_for[cid]; result = a["result"]
                versions = result.get("definition_versions", {})
                if scheme == "ORIGINAL42" and ("revised42" in versions or result.get("input_condition_scheme") == "REVISED42"):
                    continue  # Archived frames are never relabelled as original.
                result_version = versions.get("v4" if scheme == "V4" else "original42", version)
                if result_version != version:
                    continue
                assessed.add(u)
                rows = {r["trigger_id"]: r for r in result.get(field, [])
                        if r["applicability"] in POSITIVE and (axis == "DESCRIPTION" or r["relation"] == "MATCH")}
                valid = {d["id"] for d in definitions}
                labels = set(rows) & valid
                by_unit[u].update(labels)
                if result.get("classification_contract") != "SPARSE_SCENARIOS_V5":
                    if labels:
                        legacy_without_scenarios.add(u)
                    continue  # Never invent one scenario from a legacy assessment.
                scenario_ids = {s["scenario_id"] for s in result.get("scenarios", [])}
                for link in result.get("label_links", []):
                    if link["scheme"] != scheme or link["definition_version"] != version or link["trigger_id"] not in labels:
                        continue
                    for sid in link["scenario_ids"]:
                        if sid in scenario_ids:
                            # A local s1 in another issue/assessment is a different scenario.
                            key = (u, a["assessment_id"], sid)
                            scenario_sets.setdefault(key, set()).add(link["trigger_id"])
            exact = {}
            pair_units = {}; same_units = {}
            for u, labels in by_unit.items():
                exact.setdefault(tuple(sorted(labels)), set()).add(u)
                for pair in combinations(sorted(labels), 2):
                    pair_units.setdefault(pair, set()).add(u)
            for (u, _, _), labels in scenario_sets.items():
                for pair in combinations(sorted(labels), 2):
                    same_units.setdefault(pair, set()).add(u)
            groups = [{"categories": list(k), "unit_ids": sorted(v), "count": len(v)} for k, v in exact.items()]
            pairs = [{"categories": list(k), "unit_ids": sorted(v), "count": len(v),
                "same_scenario_unit_ids": sorted(same_units.get(k, set())),
                "same_scenario_count": len(same_units.get(k, set()))} for k, v in pair_units.items()]
            groups.sort(key=lambda g: (-g["count"], g["categories"]))
            pairs.sort(key=lambda p: (-p["count"], p["categories"]))
            assert sum(g["count"] for g in groups) == len(units)
            assert all(p["same_scenario_count"] <= p["count"] for p in pairs)
            output.append({"scheme": scheme, "definition_version": version, "axis": axis,
                "counting_unit": "mode_id" if init else "case_id", "unit_count": len(units),
                "assessed_unit_count": len(assessed), "unassessed_unit_ids": sorted(set(units) - assessed),
                "unlabeled_unit_ids": sorted(u for u in assessed if not by_unit[u]),
                "legacy_labeled_units_without_scenarios": sorted(legacy_without_scenarios),
                "categories": [{"id": d["id"], "name": d.get("name", d["id"]),
                    "count": sum(d["id"] in labels for labels in by_unit.values())} for d in definitions],
                "exact_combinations": groups, "pairs": pairs,
                "semantics": "Recorded label sets only; omission is NOT_ASSESSED. Co-occurrence is not causality or a sufficient trigger."})
    return {"frames": output, "unit_ids": units, "assessments_counted": len(assessments),
            "source_cases": {u: sorted(cid for cid, unit in unit_for.items() if unit == u) for u in units}}
