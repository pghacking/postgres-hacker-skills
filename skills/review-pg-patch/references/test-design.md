# Validation design

## Functional features

Choose the native PostgreSQL harness:

- `src/test/regress`: stable SQL-visible semantics and errors.
- TAP (`t/*.pl`): processes, clients, filesystem, replication, recovery, and command-line tools.
- `src/test/isolation`: concurrent schedules, locks, visibility, and deadlocks.
- module-local regression tests: extension or subsystem-specific behavior.

For each case record setup, action, expected result, and the bug it detects. Include a control path that does not use the feature. Prefer deterministic output and avoid timing assertions.

## Performance features

Define one falsifiable hypothesis. Compare equivalent baseline and patched builds with identical compiler flags, configuration, data, and host state. Include correctness checks before timing.

Specify:

- workload and data distribution;
- scale, selectivity, row width, cache state, and concurrency matrix;
- warmup and measured repetitions;
- latency distribution, throughput, CPU, I/O, memory, planning time, or WAL metrics as relevant;
- raw machine-readable output;
- variance and an acceptance/regression threshold chosen before results are seen.

Do not use a single `EXPLAIN ANALYZE` as performance proof. Report neutral or negative results as carefully as improvements.
