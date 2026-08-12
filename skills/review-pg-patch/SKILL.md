---
name: review-pg-patch
description: Review PostgreSQL patches with persistent, traceable historical memory. Use when an agent needs to review a PostgreSQL patch set, ingest mailing-list and patch metadata, record evidence-backed findings, track whether findings were fixed or superseded, or recall related prior discussions by thread, file, symbol, subsystem, topic, or text.
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
  --superseded-by-patch-set '<new-patch-set-id>'
```

Use only the dispositions defined in [references/schema.md](references/schema.md). Do not mark a finding fixed merely because a newer patch exists.

## Report

Separate current-patch observations from historical findings. For historical findings, show disposition, applicable patch-set, source link, and whether the current patch was independently checked. Cite primary evidence near every reused conclusion.
