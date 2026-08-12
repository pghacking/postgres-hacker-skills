# postgres-hacker-skills

Portable agent skills for PostgreSQL hackers: mailing-list research, patch review, and backend source explanation.

## Available skills

### `search-pg-hackers`

Searches the official PostgreSQL mailing-list archive, reconstructs complete threads, discovers patch attachments, and guides review-history and commit-status analysis.

Queries may be full titles, incomplete subject prefixes, keywords, authors, or Message-IDs. For example, `[PATCH] Avoid uninitialized-value error in` is sufficient to locate the full thread title.

Install it for a supported agent with the [skills CLI](https://www.skills.sh/docs/cli):

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills --skill search-pg-hackers
```

### `review-pg-patch`

Stores evidence-backed PostgreSQL review findings in a local SQLite database, tracks their lifecycle across patch sets, and recalls related history by thread, file, symbol, subsystem, topic, or full text.

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills --skill review-pg-patch
```

Install both skills for the complete archive-to-review-memory workflow.

The CLI detects supported agents and can also target one explicitly with its `--agent` option. Preview the repository and skill contents before installation.

Example prompts:

```text
Use $search-pg-hackers to summarize the thread "Fix small psql slash option leaks".
```

```text
Find the pgsql-hackers discussion for this Message-ID and tell me whether its patch was committed or backpatched.
```

```text
Use $review-pg-patch to review this patch and recall related findings for the touched files and symbols.
```

## Repository layout

Each directory under `skills/` is an independently installable skill containing its own `SKILL.md` and bundled resources.

```text
skills/
├── search-pg-hackers/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   └── scripts/
└── review-pg-patch/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/
    └── scripts/
```

[![skills.sh](https://skills.sh/b/pghacking/postgres-hacker-skills)](https://skills.sh/pghacking/postgres-hacker-skills)
