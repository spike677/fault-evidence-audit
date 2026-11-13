"""Fetch and inspect public official-source evidence without desktop automation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/evidence/followup_http"


def load(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.links = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "a" and not self.skip:
            self.link = {"href": attributes.get("href", ""), "parts": []}

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip -= 1
        if tag == "a" and self.link:
            self.links.append({"href": self.link["href"], "text": " ".join(self.link["parts"])})
            self.link = None

    def handle_data(self, value):
        if not self.skip and value.strip():
            self.parts.append(value.strip())
            if self.link:
                self.link["parts"].append(value.strip())


def fetch(job):
    url = job["url"]
    host = urlsplit(url).hostname
    if host not in {"gitcode.com", "raw.gitcode.com", "api.gitcode.com", "api.atomgit.com"}:
        raise ValueError(f"Unexpected host: {url}")
    key = "HTTP-" + sha256(url.encode()).hexdigest()[:20]
    folder = OUT / "http"
    meta_file = folder / (key + ".json")
    if meta_file.is_file():
        return {**job, **load(meta_file), "reused_current_run_fetch": True}
    folder.mkdir(parents=True, exist_ok=True)
    status, final_url, error = None, url, None
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=22) as response:
            raw = response.read()
            status = response.status
            final_url = response.url
    except HTTPError as exc:
        raw, status, error = exc.read(), exc.code, str(exc)
    except Exception as exc:
        raw, error = b"", f"{type(exc).__name__}: {exc}"
    text = raw.decode("utf-8", errors="replace")
    is_html = text.lstrip().lower().startswith(("<!doctype", "<html"))
    links = []
    if is_html:
        page = Page()
        page.feed(text)
        visible = "\n".join(page.parts)
        links = [{"url": urljoin(final_url, link["href"]), "text": link["text"]} for link in page.links]
    else:
        visible = text
    extension = ".html" if is_html else ".diff" if text.startswith("diff --git") else ".txt"
    raw_file = folder / (key + extension)
    text_file = folder / (key + ".visible.txt")
    raw_file.write_bytes(raw)
    text_file.write_text(visible, encoding="utf-8")
    outcome = "READABLE" if status == 200 and visible.strip() else "READ_BLOCKED"
    if status == 200 and is_html and job.get("kind") in {"DIFF", "PATCH", "SOURCE"}:
        outcome = "UNEXPECTED_HTML_INSTEAD_OF_SOURCE"
    meta = {
        "resource_id": key, "url": url, "final_url": final_url,
        "status": status, "outcome": outcome, "error": error,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "tool": "PYTHON_URLLIB_PUBLIC_HTTP_NO_COMPUTER_USE",
        "bytes": len(raw), "sha256": sha256(raw).hexdigest(),
        "raw_file": raw_file.relative_to(OUT).as_posix(),
        "text_file": text_file.relative_to(OUT).as_posix(),
        "visible_chars": len(visible), "links": links,
        "capture_scope": "COMPLETE_HTTP_RESPONSE",
        "semantic_read_scope": "NOT_REVIEWED_UNTIL_EXPLICIT_AGENT_REVIEW",
    }
    save(meta_file, meta)
    return {**job, **meta, "reused_current_run_fetch": False}


def collect_http(plan_file):
    jobs = load(plan_file)
    collected = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(fetch, jobs):
            collected.append(result)
            candidates = []
            if result.get("kind") == "SEARCH" and result["outcome"] == "READABLE":
                path = urlsplit(result["url"]).path
                repo = "/".join(path.strip("/").split("/")[:2])
                for link in result["links"]:
                    if re.fullmatch(rf"/{re.escape(repo)}/(?:issues|pull|merge_requests)/\d+", urlsplit(link["url"]).path, re.I):
                        if not any(c["url"] == link["url"] for c in candidates):
                            candidates.append(link)
                result["candidates"] = candidates
                result["search_outcome"] = "CANDIDATES_RETURNED" if candidates else "NO_VISIBLE_CANDIDATE_IN_THIS_QUERY"
            print(json.dumps({"job_id": result["job_id"], "task_ids": result["task_ids"],
                              "resource_id": result["resource_id"], "outcome": result["outcome"],
                              "candidates": candidates, "visible_chars": result["visible_chars"]}, ensure_ascii=False))
    save(OUT / "collection" / plan_file.name, collected)


def inspect(resource_ids, max_chars):
    for key in resource_ids:
        meta = load(OUT / "http" / (key + ".json"))
        text = (OUT / meta["text_file"]).read_text(encoding="utf-8")
        print(json.dumps({"resource_id": key, "url": meta["url"], "total_chars": len(text),
                          "selection_start": 0, "selection_end": min(len(text), max_chars)}, ensure_ascii=False))
        print(text[:max_chars])


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["http", "inspect"])
    parser.add_argument("values", nargs="+")
    parser.add_argument("--max-chars", type=int, default=10000)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.out.resolve()
    if OUT.is_relative_to((ROOT/'reports/archive').resolve()):
        raise ValueError('Archived evidence is read-only; select a new --out directory')
    if args.action == "http":
        collect_http(Path(args.values[0]))
    else:
        inspect(args.values, args.max_chars)


if __name__ == "__main__":
    main()
