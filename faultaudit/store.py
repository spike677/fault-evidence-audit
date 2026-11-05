"""Append-preserving SQLite records and content-addressed evidence snapshots."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .contracts import EvidencePackage, ReferenceOccurrence


class AuditError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    content = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def canonical_url(url: str) -> str:
    """Normalize host/scheme only; paths, query and fragments retain identity."""
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise AuditError("Evidence URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise AuditError("Evidence URL must not contain credentials")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path,
                       parsed.query, parsed.fragment))


def segments_for(text: str, snapshot_id: str, size: int = 6000) -> list[dict]:
    segments = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            newline = text.rfind("\n", start + size // 2, end)
            if newline > start:
                end = newline + 1
        segments.append({"segment_id": f"{snapshot_id}:s{len(segments) + 1}",
                         "start": start, "end": end, "text": text[start:end]})
        start = end
    return segments


def evidence_completeness_errors(package: dict) -> list[str]:
    """Check a collector's completeness declaration without fetching anything.

    Legacy generic packages still require only body=COMPLETE. Explicit required
    components and recognizable PRs add mechanical requirements; an untyped
    body-only package does not establish whole-site completeness for Wiki/DTS.
    """
    if package["status"] != "COMPLETE":
        return []
    errors = []
    components = package["components"]
    if not package["text"].strip():
        errors.append("COMPLETE evidence must include nonempty extracted text")
    if components.get("body") != "COMPLETE":
        errors.append("COMPLETE evidence must declare components.body=COMPLETE")
    incomplete = sorted(name for name, status in components.items()
                        if status not in {"COMPLETE", "NOT_APPLICABLE"})
    if incomplete:
        errors.append("COMPLETE evidence declares incomplete components: " + ", ".join(incomplete))
    for name in package["required_components"]:
        if not name.strip() or components.get(name) not in {"COMPLETE", "NOT_APPLICABLE"}:
            errors.append("Required evidence component is missing or incomplete: " + repr(name))
    urls = (package["url"], package.get("requested_url"), package.get("final_url"))
    is_pr = package["artifact_type"] == "PR" or any(
        url and re.search(r"/(?:pull|pulls|pull_requests|merge_requests|pr)/\d+(?:/|$)",
                          urlsplit(url).path, re.IGNORECASE) for url in urls
    )
    if is_pr:
        for name in ("file_list", "diff"):
            if components.get(name) != "COMPLETE":
                errors.append("COMPLETE PR evidence requires components." + name + "=COMPLETE")
        expected, captured = package["expected_file_count"], package["captured_file_count"]
        if expected is None or captured is None:
            errors.append("COMPLETE PR evidence requires expected_file_count and captured_file_count")
        elif expected != captured:
            errors.append("PR changed-file count does not match captured-file count")
    return errors


def authentication_page(package: dict) -> bool:
    """Reject explicit authentication redirects and unmistakable login forms.

    A sentence quoting a login prompt inside technical documentation is not
    sufficient. URL redirects are assessed separately from text length.
    """
    requested = urlsplit(package.get("requested_url") or package["url"])
    final = urlsplit(package.get("final_url") or package["url"])
    auth_path = re.search(r"/(?:login|signin|sign-in|sso|oauth2?/authorize)(?:[/.]|$)",
                          final.path, re.IGNORECASE)
    auth_host = (final.hostname or "").lower().startswith(("login.", "signin.", "sso.", "auth."))
    redirected = (requested.hostname, requested.path) != (final.hostname, final.path)
    if redirected and (auth_host or auth_path):
        return True
    text = package["text"].lower().strip()
    html_page = re.match(r"(?:<!doctype html[^>]*>\s*)?<html(?:\s|>)", text) is not None
    html_form = bool(html_page and re.search(r"<form\b", text) and re.search(
        r"<input\b[^>]*\btype\s*=\s*['\"]?password\b", text))
    login_prompt = any(token in text for token in
                       ("please sign in", "sign in to continue", "请登录后", "统一身份认证登录"))
    if html_form and login_prompt:
        return True
    # Preserve rejection of small extracted login screens, but not documents
    # that merely mention authentication in an otherwise substantive body.
    return len(text) < 400 and any(text.startswith(token) for token in
                                  ("please sign in", "sign in to continue", "请登录后", "统一身份认证登录"))


class Store:
    def __init__(self, root: str | Path, *, read_only: bool = False):
        self.root = Path(root).resolve()
        if read_only:
            self.conn = sqlite3.connect((self.root / "audit.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA query_only=ON")
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.root / "audit.sqlite3", timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
          CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, config TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS records (
            run_id TEXT NOT NULL REFERENCES runs(run_id), kind TEXT NOT NULL,
            id TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(run_id, kind, id));
          CREATE TABLE IF NOT EXISTS tasks (
            run_id TEXT NOT NULL REFERENCES runs(run_id), task_id TEXT NOT NULL,
            kind TEXT NOT NULL, target_id TEXT NOT NULL, input_hash TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
            PRIMARY KEY(run_id, task_id));
          CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            event_type TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def create_run(self, config: dict | None = None, run_id: str | None = None) -> str:
        run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        if self.conn.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
            return run_id
        with self.conn:
            self.conn.execute("INSERT INTO runs VALUES (?,?,?)", (run_id, now(), canonical_json(config or {})))
        return run_id

    def run_info(self, run_id: str | None) -> dict:
        if not run_id or run_id == "latest":
            row = self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        else:
            row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise AuditError("Run not found; import input or run demo first")
        return {"run_id": row["run_id"], "created_at": row["created_at"],
                "config": json.loads(row["config"])}

    def put(self, run_id: str, kind: str, record_id: str, payload: dict,
            *, mutable: bool = False) -> None:
        encoded = canonical_json(payload)
        existing = self.conn.execute("SELECT payload FROM records WHERE run_id=? AND kind=? AND id=?",
                                     (run_id, kind, record_id)).fetchone()
        if existing and existing["payload"] != encoded and not mutable:
            raise AuditError(f"Immutable record differs: {kind}/{record_id}")
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?)",
                              (run_id, kind, record_id, encoded))

    def get(self, run_id: str, kind: str, record_id: str) -> dict | None:
        row = self.conn.execute("SELECT payload FROM records WHERE run_id=? AND kind=? AND id=?",
                                (run_id, kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def records(self, run_id: str, kind: str) -> list[dict]:
        return [json.loads(row[0]) for row in self.conn.execute(
            "SELECT payload FROM records WHERE run_id=? AND kind=? ORDER BY id", (run_id, kind))]

    def event(self, run_id: str, event_type: str, payload: dict) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO events(run_id,event_type,created_at,payload) VALUES(?,?,?,?)",
                              (run_id, event_type, now(), canonical_json(payload)))

    def events(self, run_id: str, event_type: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM events WHERE run_id=?", [run_id]
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        return [{"seq": row["seq"], "type": row["event_type"], "created_at": row["created_at"],
                 **json.loads(row["payload"])} for row in self.conn.execute(sql + " ORDER BY seq", params)]

    def task(self, run_id: str, kind: str, target: str, inputs) -> dict:
        input_hash = digest(inputs)
        task_id = f"{kind}-{digest([target, input_hash])[:24]}"
        with self.conn:
            self.conn.execute("UPDATE tasks SET status='STALE',updated_at=? WHERE run_id=? AND kind=? "
                              "AND target_id=? AND task_id!=? AND status!='STALE'",
                              (now(), run_id, kind, target, task_id))
            self.conn.execute("INSERT OR IGNORE INTO tasks VALUES (?,?,?,?,?,?,0,'',?)",
                              (run_id, task_id, kind, target, input_hash, "PENDING", now()))
            current = self.conn.execute("SELECT status FROM tasks WHERE run_id=? AND task_id=?", (run_id, task_id)).fetchone()
            if current[0] == "STALE":
                record_kind = {"summarize": "summaries", "compare": "judgments", "catalog": "mappings"}.get(kind)
                cached = record_kind and self.get(run_id, record_kind, task_id)
                self.conn.execute("UPDATE tasks SET status=?,error='',updated_at=? WHERE run_id=? AND task_id=?",
                                  ("SUCCEEDED" if cached else "PENDING", now(), run_id, task_id))
        return dict(self.conn.execute("SELECT * FROM tasks WHERE run_id=? AND task_id=?",
                                      (run_id, task_id)).fetchone())

    def task_status(self, run_id: str, task_id: str, status: str, error: str = "") -> None:
        with self.conn:
            self.conn.execute("UPDATE tasks SET status=?,error=?,updated_at=?,attempts=attempts+? "
                              "WHERE run_id=? AND task_id=?",
                              (status, error[:3000], now(), int(status == "RUNNING"), run_id, task_id))

    def tasks(self, run_id: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY kind,target_id,task_id",
                                                      (run_id,))]

    def stale_tasks(self, run_id: str, snapshot_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE tasks SET status='STALE',updated_at=? "
                              "WHERE run_id=? AND (target_id=? OR target_id LIKE ? OR kind='catalog')",
                              (now(), run_id, snapshot_id, "%|" + snapshot_id))

    def ingest_evidence(self, run_id: str, package: dict, base_dir: Path | None = None) -> dict:
        pkg = EvidencePackage.model_validate(package).model_dump()
        url = canonical_url(pkg["url"])
        known_cases = {c["case_id"] for c in self.records(run_id, "cases")}
        if set(pkg["case_ids"]) - known_cases:
            raise AuditError("Evidence package refers to a case_id outside this run")
        raw_bytes = None
        if pkg["raw_file"]:
            base = (base_dir or Path.cwd()).resolve()
            target = (base / pkg["raw_file"]).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                raise AuditError("raw_file must name an existing file inside the evidence package directory")
            raw_bytes = target.read_bytes()
        text = pkg["text"]
        problems = evidence_completeness_errors(pkg)
        if problems:
            raise AuditError("; ".join(problems))
        if pkg["status"] in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and authentication_page(pkg):
            raise AuditError("Evidence resembles a login page; submit AUTH_REQUIRED instead")
        artifact_id = "artifact-" + digest(url)[:24]
        raw_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes is not None else None
        content = {k: pkg[k] for k in ("title", "text", "status", "components", "derived_from", "is_synthetic")}
        # Omit new default fields to retain snapshot IDs for legacy 1.0 packages.
        for key, default in (("artifact_type", "GENERIC"), ("required_components", []),
                             ("expected_file_count", None), ("captured_file_count", None)):
            if pkg[key] != default:
                content[key] = pkg[key]
        content["requested_url"] = pkg.get("requested_url") or pkg["url"]
        content["final_url"] = pkg.get("final_url") or pkg["url"]
        canonical_url(content["requested_url"])
        canonical_url(content["final_url"])
        snapshot_id = "snapshot-" + digest([url, raw_hash, content])[:24]
        snapdir = self.root / "snapshots" / snapshot_id
        snapdir.mkdir(parents=True, exist_ok=True)
        text_path = snapdir / "text.txt"
        encoded = text.encode("utf-8")
        if text_path.exists() and text_path.read_bytes() != encoded:
            raise AuditError("Saved snapshot text was altered")
        text_path.write_bytes(encoded)
        if raw_bytes is not None:
            (snapdir / "raw.bin").write_bytes(raw_bytes)
        snapshot = {"snapshot_id": snapshot_id, "artifact_id": artifact_id, "url": url,
                    **content, "text_sha256": hashlib.sha256(encoded).hexdigest(),
                    "raw_sha256": raw_hash, "raw_content_path": str(snapdir / "raw.bin") if raw_bytes is not None else None,
                    "text_path": str(text_path), "retrieved_by": pkg["retrieved_by"],
                    "retrieved_at": pkg["retrieved_at"], "segments": segments_for(text, snapshot_id)}
        if self.get(run_id, "snapshots", snapshot_id) is None:
            self.put(run_id, "snapshots", snapshot_id, snapshot)
        head = self.get(run_id, "heads", artifact_id)
        if head and head["snapshot_id"] != snapshot_id:
            self.stale_tasks(run_id, head["snapshot_id"])
            self.event(run_id, "snapshot_superseded", {"old": head["snapshot_id"], "new": snapshot_id})
        self.put(run_id, "heads", artifact_id, {"artifact_id": artifact_id, "snapshot_id": snapshot_id}, mutable=True)
        refs = self.records(run_id, "references")
        for case_id in pkg["case_ids"]:
            existing = []
            for ref in refs:
                if ref["case_id"] != case_id or not ref.get("url") or ref.get("status") != "PARSED":
                    continue
                try:
                    if canonical_url(ref["url"]) == url:
                        existing.append(ref)
                except AuditError:
                    continue
            if existing and not pkg["record_discovery"]:
                continue
            ref_id = "ref-" + digest([case_id, url, pkg["origin"], pkg["discovery_query"], pkg["discovered_from_url"]])[:24]
            ref = ReferenceOccurrence(ref_id=ref_id, case_id=case_id, raw_text=pkg["url"], url=url,
                                      origin=pkg["origin"], location=f"evidence-package:{snapshot_id}",
                                      discovered_by=pkg["retrieved_by"], discovery_query=pkg["discovery_query"],
                                      parent_url=pkg["discovered_from_url"], discovered_at=pkg["retrieved_at"]).model_dump()
            if self.get(run_id, "references", ref_id) is None:
                self.put(run_id, "references", ref_id, ref)
        self.event(run_id, "evidence_ingested", {"snapshot_id": snapshot_id, "retrieved_at": pkg["retrieved_at"],
                                               "case_ids": pkg["case_ids"], "origin": pkg["origin"]})
        return self.get(run_id, "snapshots", snapshot_id)

    def active_snapshots(self, run_id: str) -> list[dict]:
        ids = {h["snapshot_id"] for h in self.records(run_id, "heads")}
        return [s for s in self.records(run_id, "snapshots") if s["snapshot_id"] in ids]

    def verify_snapshot(self, snapshot: dict) -> list[str]:
        errors = []
        try:
            package = EvidencePackage.model_validate({key: snapshot[key] for key in EvidencePackage.model_fields
                                                      if key in snapshot}).model_dump()
            errors.extend(evidence_completeness_errors(package))
            if package["status"] in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and authentication_page(package):
                errors.append("Snapshot resembles an authentication page")
        except ValueError as exc:
            errors.append("Snapshot evidence contract is invalid: " + str(exc))
        path = Path(snapshot["text_path"])
        if not path.is_relative_to(self.root) or not path.is_file():
            return ["Snapshot text file missing or outside state directory"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["text_sha256"]:
            errors.append("Snapshot text hash mismatch")
        if hashlib.sha256(snapshot["text"].encode("utf-8")).hexdigest() != snapshot["text_sha256"]:
            errors.append("Database snapshot text hash mismatch")
        if snapshot.get("raw_content_path"):
            raw = Path(snapshot["raw_content_path"])
            if not raw.is_relative_to(self.root) or not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest() != snapshot["raw_sha256"]:
                errors.append("Snapshot raw hash mismatch")
        text = snapshot["text"]
        for segment in snapshot["segments"]:
            if text[segment["start"]:segment["end"]] != segment["text"]:
                errors.append("Snapshot segment range mismatch")
        return errors
