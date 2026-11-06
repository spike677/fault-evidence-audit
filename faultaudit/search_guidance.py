"""Agent-owned semantic query planning; the core never fabricates search words."""
from __future__ import annotations

from datetime import datetime
import re

FACET_KINDS = {"model", "operator", "symptom", "trigger", "framework", "version", "root_claim", "identifier"}


def search_guidance(case: dict, *, max_rounds: int = 3) -> dict:
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
        raise ValueError("max_search_rounds must be a positive integer")
    return {"max_rounds": max_rounds, "facet_kinds": sorted(FACET_KINDS),
        "source_cells": [{"field": field, "cell": case.get("cell_locations", {}).get(field, "")}
                         for field, value in case.get("raw", {}).items() if value],
        "instructions": (
            "Use Agent reasoning to extract source-grounded model names/aliases, complete operator names, "
            "symptoms, trigger conditions, framework/configuration, versions and supplied Wiki/DTS identifiers. Return search_facets "
            "[{kind,value,source_field,source_cell,source_quote,hypothesis}]. Each value and quote must "
            "occur in the original field; root_claim is an unverified hypothesis, not a required filter. "
            "Unknown facets stay absent, never invented. Based on actual search results, adapt combinations, "
            "source-supported aliases and implementation terms; explain relaxation of model/version or "
            "root-cause assumptions. Do not equate rope with npu_mrope or alignment64 with TP64. "
            "Return search_attempts [{round,query,scope,reason,executed,checked_at}] for actual executed "
            "queries, at most max_rounds adaptive rounds. Keep per-attempt result/candidates when present. "
            "If source content is insufficient, state input_gap rather than guessing searchable facts. "
            "Search Wiki first. Stop once the evidence plan is satisfied; do not fill every source type "
            "or expand merely to fill unknown fields. NO_MATCH is bounded by actual checked scope; "
            "login, rendering and extraction failures are BLOCKED, not an empty search result."
        )}


def validate_search_trace(case: dict, response: dict, *, max_rounds: int = 3, required: bool = False) -> list[str]:
    """Check trace provenance, not semantic quality or whether tools really ran."""
    errors = []
    facets, attempts = response.get("search_facets"), response.get("search_attempts")
    if not required and facets is None and attempts is None:
        return []
    if not isinstance(facets, list):
        errors.append("Search requires source-grounded search_facets")
        facets = []
    if not facets and not str(response.get("input_gap", "")).strip():
        errors.append("Search needs extracted facets or an explicit input_gap")
    for facet in facets:
        if not isinstance(facet, dict):
            errors.append("Search facet must be an object")
            continue
        field, quote, value = facet.get("source_field"), facet.get("source_quote", ""), facet.get("value", "")
        if (facet.get("kind") not in FACET_KINDS or field not in case.get("raw", {})
                or not isinstance(quote, str) or not quote.strip() or quote not in case["raw"].get(field, "")
                or not isinstance(value, str) or not value.strip() or value not in quote
                or not facet.get("source_cell") or facet.get("source_cell") != case.get("cell_locations", {}).get(field)):
            errors.append("Search facet must retain its exact source field, cell, quote and literal value")
        if facet.get("kind") == "root_claim" and facet.get("hypothesis") is not True:
            errors.append("Imported root-cause search facets must remain hypotheses")
        if (facet.get("kind") == "operator" and isinstance(value, str)
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", value)
                and isinstance(quote, str) and not re.search(
                    r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", quote)):
            errors.append("Search operator facet must retain the complete identifier, not a name substring")
    if not isinstance(attempts, list):
        errors.append("Search requires an actual search_attempts trace")
        attempts = []
    if not attempts and response.get("outcome") != "BLOCKED":
        errors.append("Search NO_MATCH/FOUND requires at least one executed query")
    rounds = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            errors.append("Search attempt must be an object")
            continue
        round_no = attempt.get("round")
        if (isinstance(round_no, bool) or not isinstance(round_no, int) or not 1 <= round_no <= max_rounds):
            errors.append("Search round exceeds the configured adaptive-query budget")
        else:
            rounds.append(round_no)
        if attempt.get("executed") is not True or any(not isinstance(attempt.get(key), str) or not attempt[key].strip()
                for key in ("query", "scope", "reason", "checked_at")):
            errors.append("Search attempts require actual query, scope, reason, time and execution")
        try:
            timestamp = datetime.fromisoformat(str(attempt.get("checked_at", "")).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError:
            errors.append("Search attempt time must be an ISO timestamp with timezone")
    if rounds != sorted(set(rounds)):
        errors.append("Adaptive search rounds must be unique and increasing")
    return list(dict.fromkeys(errors))
