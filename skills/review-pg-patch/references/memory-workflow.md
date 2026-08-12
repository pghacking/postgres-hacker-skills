# Review memory workflow

## Before review

1. Ingest the latest whole-thread JSON and patch-store manifest.
2. Extract exact file paths and symbols from the current patch.
3. Add a small number of subsystem and risk topics such as `wal`, `locking`, `ownership`, `error-path`, or `portability`.
4. Recall by exact targets first and free text second.

## Evaluate recalled findings

For every candidate:

- Open its source URL and verify the evidence.
- Compare its `patch_set_id` with the current content hash and lineage.
- Treat `fixed`, `rejected`, `obsolete`, and `superseded` findings as history, not current defects.
- Treat low-confidence entries as leads only.
- Recheck the current code before repeating any conclusion.

## After review

- Store one claim per finding.
- Attach file, symbol, subsystem, and topic targets conservatively.
- Preserve short evidence excerpts and stable source references.
- Update older findings when the new patch resolves or invalidates them.
- Do not store credentials, private mail, or unrelated personal information.
