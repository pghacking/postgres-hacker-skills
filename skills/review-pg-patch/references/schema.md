# Memory schema

The schema is created and migrated by `review_memory.py`.

Core entities:

- `threads`: canonical archive thread identity and last synchronization time.
- `messages`: source mail with body hash and official URL.
- `patch_sets`: independently reviewable attachment groups and their content identity.
- `findings`: one review claim with category, severity, disposition, rationale, and confidence.
- `finding_evidence`: stable source references and short supporting excerpts.
- `finding_targets`: file, symbol, subsystem, and topic keys used for recall.
- `findings_fts`: an FTS5 projection used for ranked text recall when FTS5 is available.

Allowed dispositions:

- `open`: still believed applicable.
- `accepted`: acknowledged but not yet verified fixed.
- `fixed`: verified resolved in a later patch set or commit.
- `rejected`: explicitly rejected with rationale.
- `obsolete`: no longer applicable because the design changed.
- `superseded`: replaced by another finding.

Allowed severities are `info`, `warning`, `error`, and `critical`. Confidence is `low`, `medium`, or `high`.

SQLite is the version-one storage contract. Future remote backends must preserve IDs, provenance, dispositions, and patch-set hashes.
