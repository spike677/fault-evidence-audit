"""Check a collector's page observations without fetching or guessing content.

Legacy evidence stays readable under its original contract. New workflows can
require a body observation before a Wiki satisfies their collection condition.
"""
from __future__ import annotations

from datetime import datetime

READABLE = {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}
REPAIR_KINDS = {"INDEX", "TITLE_ONLY", "RENDER_PENDING", "EXTRACTION_FAILED"}
ACCESS_KINDS = {"LOGIN", "FORBIDDEN"}


def _timestamp(value) -> bool:
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def capture_quality(package: dict, *, require_observation: bool = False) -> dict:
    """Return body usability and explicit repair/access gaps, retaining content.

    A BODY assertion needs a precise locator and source quotes. This verifies
    grounding, not that the collector actually used a browser or understood it.
    """
    observation = package.get("capture_observation")
    readable = package.get("status") in READABLE and bool(package.get("text", "").strip())
    if not observation:
        return {"status": "UNASSESSED", "usable_body": readable and not require_observation,
                "needs_repair": readable and require_observation,
                "errors": ["Capture requires a page/body observation"] if readable and require_observation else []}
    if hasattr(observation, "model_dump"):
        observation = observation.model_dump()
    errors = []
    kind = observation.get("page_kind")
    for key in ("requested_url", "final_url", "observed_by", "tool_observation"):
        if not isinstance(observation.get(key), str) or not observation[key].strip():
            errors.append("Capture observation requires " + key)
    if not _timestamp(observation.get("observed_at")):
        errors.append("Capture observation requires an ISO timestamp with timezone")
    requested = package.get("requested_url") or package.get("url")
    final = package.get("final_url") or package.get("url")
    if observation.get("requested_url") != requested or observation.get("final_url") != final:
        errors.append("Capture observation URLs must match the package requested/final URLs")
    body_kind = kind == "BODY" or kind == "UNRELATED" and bool(observation.get("body_locator") and observation.get("body_quotes"))
    if body_kind:
        quotes = observation.get("body_quotes", [])
        if not observation.get("body_locator", "").strip():
            errors.append("BODY capture requires a precise body locator")
        if not isinstance(quotes, list) or not quotes or any(
                not isinstance(quote, str) or not quote.strip() or quote not in package.get("text", "")
                for quote in quotes):
            errors.append("BODY capture requires exact nonempty body quotes in captured text")
        title = (observation.get("title") or package.get("title", "")).strip()
        if title and (package.get("text", "").strip() == title or quotes and all(
                isinstance(quote, str) and quote.strip() == title for quote in quotes)):
            errors.append("BODY capture cannot use only the page title as body evidence")
    elif kind not in REPAIR_KINDS | ACCESS_KINDS | {"UNRELATED"}:
        errors.append("Unknown page kind in capture observation")
    # Preserve any actually acquired partial text, but a navigation/login shell
    # cannot simultaneously claim that the complete document body was captured.
    if not body_kind and (package.get("status") == "COMPLETE"
            or package.get("components", {}).get("body") == "COMPLETE"):
        errors.append("Non-body page cannot declare COMPLETE document/body capture")
    return {"status": kind or "UNASSESSED", "usable_body": readable and body_kind and not errors,
            "needs_repair": kind in REPAIR_KINDS or kind == "UNRELATED" and not body_kind or bool(errors), "errors": list(dict.fromkeys(errors))}


def capture_quality_errors(package: dict, *, require_observation: bool = False) -> list[str]:
    return capture_quality(package, require_observation=require_observation)["errors"]


def collection_observation_instructions() -> str:
    return (
        "Capture actual page observations in capture_observation: page_kind "
        "BODY|INDEX|TITLE_ONLY|LOGIN|FORBIDDEN|RENDER_PENDING|EXTRACTION_FAILED|UNRELATED, "
        "requested_url, final_url, title, body_locator, body_quotes, observed_by, observed_at "
        "(ISO timezone), tool_observation. BODY needs actual body location and exact captured quotes; "
        "a title is not body evidence. INDEX/TITLE_ONLY/render/extraction failure is not search NO_MATCH. "
        "Actual unrelated body content is still BODY; assess association separately in the factual comparison. "
        "Follow an applicable index child with its navigation provenance; retain parent material. "
        "Keep acquired partial text but do not mark a non-body page/body COMPLETE. "
        "Use the existing Edge session; only the user enters credentials. Report authentication "
        "blocking for the site rather than inventing a login or asking once per case."
    )
