#!/usr/bin/env python3
"""Persist and recall evidence-backed PostgreSQL patch review findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
DISPOSITIONS = ("open", "accepted", "fixed", "rejected", "obsolete", "superseded")
SEVERITIES = ("info", "warning", "error", "critical")
CONFIDENCES = ("low", "medium", "high")
TARGET_KINDS = ("file", "symbol", "subsystem", "topic")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db() -> Path:
    configured = os.environ.get("PG_HACKER_MEMORY_DB")
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local/share"
    return root / "postgres-hacker-skills/review-memory.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    initialize(db)
    return db


def initialize(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threads (
          id INTEGER PRIMARY KEY,
          root_message_id TEXT,
          canonical_subject TEXT,
          thread_url TEXT NOT NULL UNIQUE,
          last_synced_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          message_id TEXT PRIMARY KEY,
          thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
          sender TEXT,
          sent_at TEXT,
          subject TEXT,
          url TEXT,
          body_sha256 TEXT NOT NULL,
          body TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS patch_sets (
          id TEXT PRIMARY KEY,
          thread_id INTEGER REFERENCES threads(id) ON DELETE SET NULL,
          message_id TEXT REFERENCES messages(message_id) ON DELETE SET NULL,
          subject TEXT,
          sent_at TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          content_sha256 TEXT,
          manifest_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS findings (
          id TEXT PRIMARY KEY,
          patch_set_id TEXT REFERENCES patch_sets(id) ON DELETE SET NULL,
          category TEXT NOT NULL,
          severity TEXT NOT NULL,
          claim TEXT NOT NULL,
          rationale TEXT NOT NULL DEFAULT '',
          disposition TEXT NOT NULL,
          confidence TEXT NOT NULL,
          superseded_by_finding_id TEXT REFERENCES findings(id),
          superseded_by_patch_set_id TEXT REFERENCES patch_sets(id),
          created_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS finding_evidence (
          id INTEGER PRIMARY KEY,
          finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
          message_id TEXT,
          source_url TEXT,
          source_ref TEXT,
          excerpt TEXT NOT NULL DEFAULT '',
          evidence_sha256 TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS finding_targets (
          finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          value TEXT NOT NULL,
          PRIMARY KEY (finding_id, kind, value)
        );
        CREATE INDEX IF NOT EXISTS finding_targets_lookup ON finding_targets(kind, value);
        CREATE INDEX IF NOT EXISTS findings_patch_set ON findings(patch_set_id);
        """
    )
    current = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    if current and int(current[0]) != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported schema version {current[0]}")
    db.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    try:
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS findings_fts USING fts5("
            "finding_id UNINDEXED, claim, rationale, evidence, targets)"
        )
        db.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('fts5', '1')")
    except sqlite3.OperationalError:
        db.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('fts5', '0')")
    db.commit()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def ingest(db: sqlite3.Connection, thread_path: Path | None, manifest_path: Path | None) -> dict:
    thread_id = None
    message_count = 0
    patch_count = 0
    thread = load_json(thread_path) if thread_path else None
    if thread:
        messages = thread.get("messages", [])
        root = messages[0] if messages else {}
        thread_url = thread["thread_url"]
        db.execute(
            """INSERT INTO threads(root_message_id, canonical_subject, thread_url, last_synced_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(thread_url) DO UPDATE SET
                 root_message_id=excluded.root_message_id,
                 canonical_subject=excluded.canonical_subject,
                 last_synced_at=excluded.last_synced_at""",
            (root.get("message_id"), root.get("subject"), thread_url, thread.get("retrieved_at", now())),
        )
        thread_id = db.execute("SELECT id FROM threads WHERE thread_url=?", (thread_url,)).fetchone()[0]
        for message in messages:
            body = message.get("body") or ""
            db.execute(
                """INSERT INTO messages(message_id, thread_id, sender, sent_at, subject, url, body_sha256, body)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(message_id) DO UPDATE SET
                     thread_id=excluded.thread_id, sender=excluded.sender, sent_at=excluded.sent_at,
                     subject=excluded.subject, url=excluded.url,
                     body_sha256=excluded.body_sha256, body=excluded.body""",
                (message["message_id"], thread_id, message.get("from"), message.get("date"),
                 message.get("subject"), message.get("url"),
                 hashlib.sha256(body.encode()).hexdigest(), body),
            )
            message_count += 1
    if manifest_path:
        manifest = load_json(manifest_path)
        if thread_id is None and manifest.get("thread_url"):
            row = db.execute("SELECT id FROM threads WHERE thread_url=?", (manifest["thread_url"],)).fetchone()
            thread_id = row[0] if row else None
        for patch_set in manifest.get("patch_sets", []):
            hashes = sorted(item.get("sha256", "") for item in patch_set.get("attachments", []))
            content_hash = hashlib.sha256("\n".join(hashes).encode()).hexdigest() if hashes else None
            message_id = patch_set.get("message_id")
            if message_id and not db.execute(
                "SELECT 1 FROM messages WHERE message_id=?", (message_id,)
            ).fetchone():
                message_id = None
            db.execute(
                """INSERT INTO patch_sets(id, thread_id, message_id, subject, sent_at, status,
                                            content_sha256, manifest_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     thread_id=COALESCE(excluded.thread_id, patch_sets.thread_id),
                     message_id=excluded.message_id, subject=excluded.subject, sent_at=excluded.sent_at,
                     status=excluded.status, content_sha256=excluded.content_sha256,
                     manifest_json=excluded.manifest_json, updated_at=excluded.updated_at""",
                (patch_set["id"], thread_id, message_id, patch_set.get("subject"),
                 patch_set.get("date"), patch_set.get("status", "pending"), content_hash,
                 json.dumps(patch_set, ensure_ascii=False, sort_keys=True), manifest.get("updated_at", now())),
            )
            patch_count += 1
    db.commit()
    return {"messages_ingested": message_count, "patch_sets_ingested": patch_count}


def rebuild_fts(db: sqlite3.Connection, finding_id: str) -> None:
    enabled = db.execute("SELECT value FROM metadata WHERE key='fts5'").fetchone()[0] == "1"
    if not enabled:
        return
    finding = db.execute("SELECT claim, rationale FROM findings WHERE id=?", (finding_id,)).fetchone()
    evidence = "\n".join(row[0] for row in db.execute(
        "SELECT excerpt FROM finding_evidence WHERE finding_id=?", (finding_id,)
    ))
    targets = " ".join(row[0] for row in db.execute(
        "SELECT value FROM finding_targets WHERE finding_id=?", (finding_id,)
    ))
    db.execute("DELETE FROM findings_fts WHERE finding_id=?", (finding_id,))
    db.execute(
        "INSERT INTO findings_fts(finding_id, claim, rationale, evidence, targets) VALUES (?, ?, ?, ?, ?)",
        (finding_id, finding["claim"], finding["rationale"], evidence, targets),
    )


def remember(db: sqlite3.Connection, args: argparse.Namespace) -> dict:
    if not (args.source_message_id or args.source_url or args.source_ref):
        raise RuntimeError("provide --source-message-id, --source-url, or --source-ref")
    finding_id = str(uuid.uuid4())
    timestamp = now()
    db.execute(
        """INSERT INTO findings(id, patch_set_id, category, severity, claim, rationale,
                                 disposition, confidence, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (finding_id, args.patch_set_id, args.category, args.severity, args.claim,
         args.rationale, args.disposition, args.confidence, args.created_by, timestamp, timestamp),
    )
    evidence_key = "\n".join(filter(None, [args.source_message_id, args.source_url, args.source_ref, args.evidence]))
    db.execute(
        """INSERT INTO finding_evidence(finding_id, message_id, source_url, source_ref,
                                         excerpt, evidence_sha256)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (finding_id, args.source_message_id, args.source_url, args.source_ref,
         args.evidence, hashlib.sha256(evidence_key.encode()).hexdigest()),
    )
    for kind in TARGET_KINDS:
        for value in getattr(args, kind):
            db.execute(
                "INSERT OR IGNORE INTO finding_targets(finding_id, kind, value) VALUES (?, ?, ?)",
                (finding_id, kind, value),
            )
    rebuild_fts(db, finding_id)
    db.commit()
    return finding_detail(db, finding_id)


def finding_detail(db: sqlite3.Connection, finding_id: str) -> dict:
    row = db.execute(
        """SELECT f.*, ps.content_sha256 AS patch_set_sha256, ps.subject AS patch_set_subject
           FROM findings f LEFT JOIN patch_sets ps ON ps.id=f.patch_set_id WHERE f.id=?""",
        (finding_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"finding not found: {finding_id}")
    result = dict(row)
    result["evidence"] = [dict(item) for item in db.execute(
        "SELECT message_id, source_url, source_ref, excerpt, evidence_sha256 FROM finding_evidence WHERE finding_id=?",
        (finding_id,),
    )]
    result["targets"] = [dict(item) for item in db.execute(
        "SELECT kind, value FROM finding_targets WHERE finding_id=? ORDER BY kind, value", (finding_id,)
    )]
    return result


def update_finding(db: sqlite3.Connection, args: argparse.Namespace) -> dict:
    assignments = ["updated_at=?"]
    values = [now()]
    for column in ("disposition", "superseded_by_finding_id", "superseded_by_patch_set_id"):
        value = getattr(args, column)
        if value is not None:
            assignments.append(f"{column}=?")
            values.append(value)
    values.append(args.finding_id)
    cursor = db.execute(f"UPDATE findings SET {', '.join(assignments)} WHERE id=?", values)
    if cursor.rowcount != 1:
        raise RuntimeError(f"finding not found: {args.finding_id}")
    db.commit()
    return finding_detail(db, args.finding_id)


def fts_query(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_./-]+", text)
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def recall(db: sqlite3.Connection, args: argparse.Namespace) -> dict:
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    weights = {"file": 40, "symbol": 60, "subsystem": 25, "topic": 20}
    for kind in TARGET_KINDS:
        for value in getattr(args, kind):
            for row in db.execute(
                "SELECT finding_id FROM finding_targets WHERE kind=? AND value=? COLLATE NOCASE",
                (kind, value),
            ):
                scores[row[0]] = scores.get(row[0], 0) + weights[kind]
                reasons.setdefault(row[0], []).append(f"{kind}:{value}")
    if args.thread_url:
        for row in db.execute(
            """SELECT f.id FROM findings f JOIN patch_sets ps ON ps.id=f.patch_set_id
               JOIN threads t ON t.id=ps.thread_id WHERE t.thread_url=?""",
            (args.thread_url,),
        ):
            scores[row[0]] = scores.get(row[0], 0) + 100
            reasons.setdefault(row[0], []).append("same-thread")
    if args.query:
        fts_enabled = db.execute("SELECT value FROM metadata WHERE key='fts5'").fetchone()[0] == "1"
        if fts_enabled and fts_query(args.query):
            for row in db.execute(
                "SELECT finding_id, bm25(findings_fts) FROM findings_fts WHERE findings_fts MATCH ? LIMIT ?",
                (fts_query(args.query), args.limit * 4),
            ):
                scores[row[0]] = scores.get(row[0], 0) + max(1, 15 - abs(float(row[1])))
                reasons.setdefault(row[0], []).append("full-text")
        else:
            pattern = f"%{args.query}%"
            for row in db.execute(
                "SELECT id FROM findings WHERE claim LIKE ? OR rationale LIKE ?", (pattern, pattern)
            ):
                scores[row[0]] = scores.get(row[0], 0) + 10
                reasons.setdefault(row[0], []).append("text-fallback")
    ordered = sorted(scores, key=lambda item: (-scores[item], item))[: args.limit]
    findings = []
    for finding_id in ordered:
        item = finding_detail(db, finding_id)
        item["recall_score"] = round(scores[finding_id], 3)
        item["recall_reasons"] = reasons[finding_id]
        findings.append(item)
    return {"query": args.query, "count": len(findings), "findings": findings}


def add_targets(parser: argparse.ArgumentParser) -> None:
    for kind in TARGET_KINDS:
        parser.add_argument(f"--{kind}", action="append", default=[])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="initialize the database")
    ingest_parser = commands.add_parser("ingest", help="ingest thread and patch metadata")
    ingest_parser.add_argument("--thread-json", type=Path)
    ingest_parser.add_argument("--patch-manifest", type=Path)
    remember_parser = commands.add_parser("remember", help="record one review finding")
    remember_parser.add_argument("--patch-set-id")
    remember_parser.add_argument("--category", required=True)
    remember_parser.add_argument("--severity", choices=SEVERITIES, default="warning")
    remember_parser.add_argument("--claim", required=True)
    remember_parser.add_argument("--rationale", default="")
    remember_parser.add_argument("--disposition", choices=DISPOSITIONS, default="open")
    remember_parser.add_argument("--confidence", choices=CONFIDENCES, default="high")
    remember_parser.add_argument("--created-by", default="agent")
    remember_parser.add_argument("--source-message-id")
    remember_parser.add_argument("--source-url")
    remember_parser.add_argument("--source-ref")
    remember_parser.add_argument("--evidence", default="")
    add_targets(remember_parser)
    update_parser = commands.add_parser("update", help="update a finding lifecycle")
    update_parser.add_argument("finding_id")
    update_parser.add_argument("--disposition", choices=DISPOSITIONS)
    update_parser.add_argument("--superseded-by-finding-id")
    update_parser.add_argument("--superseded-by-patch-set-id")
    recall_parser = commands.add_parser("recall", help="recall related historical findings")
    recall_parser.add_argument("--thread-url")
    recall_parser.add_argument("--query")
    recall_parser.add_argument("--limit", type=int, default=10)
    add_targets(recall_parser)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        with connect(args.db) as db:
            if args.command == "init":
                result = {"database": str(args.db.expanduser().resolve()), "schema_version": SCHEMA_VERSION}
            elif args.command == "ingest":
                if not (args.thread_json or args.patch_manifest):
                    raise RuntimeError("provide --thread-json or --patch-manifest")
                result = ingest(db, args.thread_json, args.patch_manifest)
            elif args.command == "remember":
                result = remember(db, args)
            elif args.command == "update":
                result = update_finding(db, args)
            else:
                result = recall(db, args)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    except (RuntimeError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
