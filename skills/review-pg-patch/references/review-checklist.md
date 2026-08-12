# PostgreSQL patch review checklist

Select the sections implicated by the patch; do not mechanically claim every risk applies.

## Correctness

- Check NULL, empty, minimum/maximum, overflow, malformed input, encoding, collation, and type coercion.
- Check error cleanup, partial initialization, ownership transfer, memory context lifetime, and repeated execution.
- Check transaction, subtransaction, abort, retry, prepared statement, and cached-plan behavior.
- Check catalog invalidation, dependency tracking, dump/restore, upgrade, and extension compatibility.

## Concurrency and durability

- Identify every lock and required ordering; inspect paths reached before and after acquisition.
- Check snapshot visibility, interrupts, cancellation, deadlock, standby, parallel worker, and background worker behavior.
- For persistent state, check WAL logging, replay, crash boundaries, checksums, and replication.

## Planner and executor

- Check estimates, parameterization, rescans, EPQ, partitioning, parallel safety, volatile expressions, and disabled plan types.
- Verify optimized and fallback paths return identical results.

## Interfaces

- Check SQL grammar ambiguity, error location, tab completion, psql scripting, libpq modes, privileges, and documentation.
- Check supported compilers, operating systems, integer widths, optional libraries, and translations.

## Evidence

- Read surrounding source and callers, not only the diff.
- Reproduce a suspected issue or give a precise execution path.
- Separate existing defects from regressions introduced by the patch.
