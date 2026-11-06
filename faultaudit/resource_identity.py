"""Navigation identity for known evidence resources, never incident identity.

Stored source URLs and fragment locators remain untouched. These keys let the
planner reuse a full-resource capture while preserving each occurrence's trace.
Unknown URLs retain their query and fragment, and version/ref parameters remain
meaningful on every platform.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def resource_url(url: str) -> str:
    """Return a fetch/navigation URL for a recognized resource or the input URL.

    Only known tracking query keys and navigation fragments are removed. Do not
    generalize this to blob paths, arbitrary query parameters or unknown hosts.
    """
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Resource URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("Resource URL must not contain credentials")
    host, path = parsed.hostname.casefold(), parsed.path
    netloc = parsed.netloc.casefold()
    known = False
    if host in {"github.com", "www.github.com", "gitcode.com", "www.gitcode.com", "gitee.com", "www.gitee.com"}:
        match = re.fullmatch(r"/([^/]+)/([^/]+)/(pulls?|issues|pull_requests|merge_requests)/(\d+)(?:/(?:files|commits|checks))?/?", path)
        if match:
            owner, repo, kind, number = match.groups()
            if host in {"github.com", "www.github.com"}:
                owner, repo = owner.casefold(), repo.casefold()
                if kind in {"pull", "pulls"}:
                    kind = "pull"
                netloc = "github.com" + (":" + str(parsed.port) if parsed.port else "")
            path = f"/{owner}/{repo}/{kind}/{number}"
            known = True
    elif host.startswith("wiki.") and re.search(r"/WIKI\d+/?$", path, re.IGNORECASE):
        # Keep domain/space path components: a bare page number is not a
        # globally unique resource or a reason to merge different Wiki spaces.
        path = path.rstrip("/")
        known = True
    elif (host.startswith(("dts.", "dts-")) or re.search(r"/DTSPortal/", path, re.IGNORECASE)) and re.search(r"/DTS\d+/?$", path, re.IGNORECASE):
        path = path.rstrip("/")
        known = True
    if known:
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid"}]
        # Sorting query keys equates syntactic ordering only, retaining every
        # value (including repeated parameter values) and meaningful ref/version.
        query = sorted(enumerate(query), key=lambda item: (item[1][0], item[0]))
        query_text = urlencode([pair for _, pair in query])
        fragment = ""
    else:
        query_text, fragment = parsed.query, parsed.fragment
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query_text, fragment))


def resource_key(url: str) -> str:
    """Stable platform resource identity; not an event/group identifier."""
    return resource_url(url)


def same_resource(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    try:
        return resource_key(left) == resource_key(right)
    except (TypeError, ValueError):
        return False


def _capture_order(snapshot: dict) -> tuple:
    raw = str(snapshot.get("retrieved_at") or "")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        stamp = parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except (ValueError, OverflowError):
        stamp = float("-inf")
    return stamp, raw, str(snapshot.get("snapshot_id", ""))


def snapshot_index(snapshots: list[dict]) -> dict[str, dict]:
    """Index current captures by resource, taking the latest declared capture.

    A newer access failure must not be hidden by preferring an older readable
    alias. Callers still verify completeness, integrity and applicability.
    """
    result = {}
    for snapshot in sorted(snapshots, key=_capture_order):
        try:
            result[resource_key(snapshot["url"])] = snapshot
        except (KeyError, TypeError, ValueError):
            continue
    return result
