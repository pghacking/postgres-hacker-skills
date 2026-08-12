---
name: review-pg-patch
description: Review PostgreSQL patches, design functional SQL/TAP/isolation tests and performance experiments, and retain traceable historical memory. Use when an agent needs to inspect a PostgreSQL patch set against a source tree, assess correctness and subsystem risks, produce runnable validation plans, ingest mailing-list context, record evidence-backed findings, or recall related prior discussions.
---

# Review PostgreSQL Patches

Use a local SQLite database to retain review knowledge across sessions. Treat the database as an index of claims and provenance, not as a replacement for the source thread or patch.

Set `PG_HACKER_MEMORY_DB` to select a database. Otherwise use `~/.local/share/postgres-hacker-skills/review-memory.sqlite3`.

## Prepare context

Use `search-pg-hackers` to retrieve the thread and persistent patch store. Save its thread JSON, then ingest both artifacts:

```bash
python3 scripts/review_memory.py ingest \
  --thread-json thread.json \
  --patch-manifest thread-work/manifest.json
```

Before reviewing, extract changed file paths, important symbols, subsystem names, and topics. Recall related findings:

```bash
python3 scripts/review_memory.py recall \
  --file src/backend/example.c \
  --symbol ExampleFunction \
  --topic concurrency \
  --query "error cleanup"
```

Read [references/memory-workflow.md](references/memory-workflow.md) before using recalled findings. Never repeat a recalled claim without checking its evidence and applicability to the current patch hash.

## Inspect the patch

Generate a deterministic inventory before reasoning about behavior:

```bash
python3 scripts/patch_review.py inspect \
  --patch-dir thread-work/patch-sets/<patch-set-id> \
  --source-tree /path/to/postgres \
  --output review-work/inspection.json
```

Read every patch in series order and the complete affected functions in the source tree. Trace callers, callees, ownership, locks, transaction boundaries, error paths, catalog/WAL effects, and platform-dependent branches. Do not limit review to changed lines. Use [references/review-checklist.md](references/review-checklist.md) to select relevant risks.

Distinguish an observation from a defect. Record a finding only when you can explain the failing invariant, triggering path, and user-visible or developer-visible consequence. Include file and line evidence from the patched result whenever possible.

## Design validation

For SQL-visible behavior, generate a functional test-plan scaffold:

```bash
python3 scripts/patch_review.py plan-tests \
  --inspection review-work/inspection.json \
  --kind functional \
  --output review-work/functional
```

Complete `test.sql` with normal, boundary, NULL, invalid-input, transaction, privilege, prepared-statement, partitioning, dump/restore, and configuration cases that apply. Put stable behavior in regression tests, frontend behavior in TAP, and concurrency schedules in isolation specs. State the expected result and failure oracle for every case; never invent expected semantics when the thread or documentation is ambiguous.

For performance claims, generate an experiment scaffold:

```bash
python3 scripts/patch_review.py plan-tests \
  --inspection review-work/inspection.json \
  --kind performance \
  --output review-work/performance
```

Complete the hypothesis, baseline/patched builds, workload matrix, warmup, repetitions, cache state, concurrency, metrics, correctness guard, and regression threshold. Prefer giving the user reproducible commands to run on a controlled host. Analyze raw results only after checking variance and environmental comparability. Read [references/test-design.md](references/test-design.md).

## Record findings

Record one independently actionable claim per finding:

```bash
python3 scripts/review_memory.py remember \
  --patch-set-id '<patch-set-id>' \
  --category resource-management \
  --severity warning \
  --claim 'The error path does not release the parsed option.' \
  --rationale 'The callee returns malloc-owned memory.' \
  --source-message-id '<message-id>' \
  --source-url '<official-message-url>' \
  --evidence '<short supporting excerpt>' \
  --file src/bin/psql/command.c \
  --symbol exec_command_getresults \
  --topic ownership
```

Require a source URL, source Message-ID, or another stable source reference. Mark inference through `--confidence low|medium`; do not present it as thread consensus.

## Update lifecycle

Update a finding after checking a later patch set or discussion:

```bash
python3 scripts/review_memory.py update <finding-id> \
  --disposition fixed \
  --superseded-by-patch-set-id '<new-patch-set-id>'
```

Use only the dispositions defined in [references/schema.md](references/schema.md). Do not mark a finding fixed merely because a newer patch exists.

## Report

Separate current-patch observations from historical findings. For historical findings, show disposition, applicable patch-set, source link, and whether the current patch was independently checked. Cite primary evidence near every reused conclusion.
