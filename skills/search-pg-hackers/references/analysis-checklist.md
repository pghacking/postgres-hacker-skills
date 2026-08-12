# Thread analysis checklist

## Identity

- Confirm the canonical subject, root Message-ID, list, author, and start date.
- Collapse `Re:` and patch-version subject variants into one thread.
- Check whether discussion continued under a renamed subject.

## Patch history

- Record every visible patch version and attachment URL.
- Sync attachments into a persistent patch store before review.
- Treat all attachments on one message as one independently reviewable patch set.
- Mark a patch set `reviewed` only after completing its review; do not use the arrival of a later version as a substitute.
- Preserve old patch-set directories for comparison and use the manifest hashes to avoid duplicate downloads.
- Attribute proposed changes to the correct author and message.
- Separate code-review feedback from design objections and testing reports.

## Status

- Treat “I will commit” or “looks good” as intent, not a commit.
- Verify commits in PostgreSQL Git by subject, author, touched symbols, or patch content.
- Verify CommitFest state separately when the thread concerns a tracked patch.
- Verify which release branches received a backpatch.
- State “not found as of <time>” when evidence is incomplete.

## Output

- Give a concise current conclusion.
- Summarize the chronology and major technical decisions.
- List unresolved issues or follow-up work.
- Link primary messages, patch attachments, CommitFest entries, and commits near the claims they support.
- Mark any inference explicitly.
