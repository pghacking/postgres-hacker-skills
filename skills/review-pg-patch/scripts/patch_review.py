#!/usr/bin/env python3
"""Inventory PostgreSQL patch sets and create validation-plan scaffolds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def patch_files(directory: Path) -> list[Path]:
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if not files:
        raise RuntimeError(f"no patch files found in {directory}")
    return files


def classify(paths: list[str], text: str) -> tuple[list[str], list[str]]:
    joined = "\n".join(paths) + "\n" + text
    subsystems = set()
    risks = set()
    rules = [
        (r"src/backend/(optimizer|executor)/", "planner-executor", "plan-correctness"),
        (r"src/backend/(access/transam|replication)/|\bXLog|\bWAL\b", "wal-replication", "durability"),
        (r"src/backend/parser/|gram\.y|src/include/catalog/", "sql-catalog", "compatibility"),
        (r"src/bin/psql/", "psql", "client-state"),
        (r"src/test/perl/|/t/\d+_", "tap-tests", "portability"),
        (r"Lock|LWLock|spinlock|snapshot|concurrent", "concurrency", "race-deadlock"),
        (r"MemoryContext|palloc|pfree|malloc|free\(", "memory", "ownership-lifetime"),
        (r"postgres_fdw|foreign/", "fdw", "remote-semantics"),
    ]
    for pattern, subsystem, risk in rules:
        if re.search(pattern, joined, re.I):
            subsystems.add(subsystem)
            risks.add(risk)
    return sorted(subsystems), sorted(risks)


def inspect(directory: Path, source_tree: Path | None) -> dict:
    series = []
    all_paths = []
    all_text = []
    for path in patch_files(directory):
        payload = path.read_bytes()
        text = payload.decode("utf-8", "replace")
        paths = []
        for match in re.finditer(r"^diff --git a/(.+?) b/(.+?)$", text, re.M):
            paths.extend(match.groups())
        paths = sorted(set(paths))
        all_paths.extend(paths)
        all_text.append(text)
        series.append({
            "name": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "subject": next((line[9:] for line in text.splitlines() if line.startswith("Subject: ")), None),
            "files": paths,
            "hunks": len(re.findall(r"^@@ ", text, re.M)),
            "additions": len(re.findall(r"^\+(?!\+\+)", text, re.M)),
            "deletions": len(re.findall(r"^-(?!--)", text, re.M)),
        })
    changed = sorted(set(all_paths))
    subsystems, risks = classify(changed, "\n".join(all_text))
    source = None
    missing = []
    if source_tree:
        source = str(source_tree.resolve())
        missing = [item for item in changed if not (source_tree / item).exists()]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patch_directory": str(directory.resolve()),
        "source_tree": source,
        "series_sha256": hashlib.sha256("\n".join(item["sha256"] for item in series).encode()).hexdigest(),
        "patches": series,
        "changed_files": changed,
        "missing_source_files": missing,
        "suggested_subsystems": subsystems,
        "suggested_risks": risks,
        "review_requirements": [
            "Read complete affected functions and relevant callers/callees.",
            "Recall historical findings for changed files, symbols, subsystems, and risks.",
            "Verify each finding against the patched result and a reproducible path.",
        ],
    }


def write_functional(output: Path, inspection: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "test.sql").write_text(
        "-- PostgreSQL functional validation scaffold\n"
        "-- Replace placeholders with cases justified by the patch semantics.\n\n"
        "-- setup\n\n-- normal and control paths\n\n-- NULL and boundary inputs\n\n"
        "-- invalid inputs and expected errors\n\n-- transaction and prepared-statement behavior\n\n-- cleanup\n"
    )
    plan = {
        "kind": "functional",
        "series_sha256": inspection["series_sha256"],
        "candidate_harnesses": ["regression-sql", "tap", "isolation"],
        "cases": [
            {"name": name, "setup": "TODO", "action": "TODO", "expected": "TODO", "oracle": "TODO"}
            for name in ("control", "normal", "null-boundary", "invalid-input", "transaction", "privilege")
        ],
        "changed_files": inspection["changed_files"],
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")


def write_performance(output: Path, inspection: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "kind": "performance",
        "series_sha256": inspection["series_sha256"],
        "hypothesis": "TODO: one falsifiable performance claim",
        "builds": {"baseline": "TODO commit/build", "patched": "TODO commit/build"},
        "controls": ["identical compiler flags", "identical postgresql.conf", "correctness guard", "controlled host state"],
        "matrix": {"scale": [], "distribution": [], "cache_state": ["warm"], "concurrency": [1]},
        "execution": {"warmup_runs": 3, "measured_runs": 10, "randomize_build_order": True},
        "metrics": ["wall_time", "throughput", "cpu", "io", "memory", "planning_time", "wal_bytes"],
        "acceptance_threshold": "TODO before running",
        "changed_files": inspection["changed_files"],
    }
    (output / "experiment.json").write_text(json.dumps(plan, indent=2) + "\n")
    (output / "run.sh").write_text(
        "#!/bin/sh\nset -eu\n\n"
        "# Fill in explicit baseline and patched commands. Emit raw results; do not summarize here.\n"
        "echo 'TODO: benchmark runner' >&2\nexit 2\n"
    )
    (output / "run.sh").chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--patch-dir", type=Path, required=True)
    inspect_parser.add_argument("--source-tree", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)
    plan_parser = commands.add_parser("plan-tests")
    plan_parser.add_argument("--inspection", type=Path, required=True)
    plan_parser.add_argument("--kind", choices=("functional", "performance"), required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = inspect(args.patch_dir, args.source_tree)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
        else:
            inspection = json.loads(args.inspection.read_text())
            if args.kind == "functional":
                write_functional(args.output, inspection)
            else:
                write_performance(args.output, inspection)
            print(json.dumps({"kind": args.kind, "output": str(args.output.resolve())}, indent=2))
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
