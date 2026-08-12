# postgres-hacker-skills

Portable agent skills for PostgreSQL hackers: mailing-list research, patch review, and backend source explanation.

## Installation

Install all skills in this repository for the complete archive-to-review-memory workflow:

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills
```

The CLI discovers every `SKILL.md` in the repository and configures the selected skills for a supported agent. Use `--skill` only when you want one capability instead of the full collection:

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills \
  --skill search-pg-hackers
```

The CLI can also target an agent explicitly with its `--agent` option. Preview the repository and skill contents before installation.

## Available skills

### `search-pg-hackers`

Searches the official PostgreSQL mailing-list archive, reconstructs complete threads, discovers patch attachments, and guides review-history and commit-status analysis.

Queries may be full titles, incomplete subject prefixes, keywords, authors, or Message-IDs. For example, `[PATCH] Avoid uninitialized-value error in` is sufficient to locate the full thread title.

Install only this skill with the [skills CLI](https://www.skills.sh/docs/cli):

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills --skill search-pg-hackers
```

### `review-pg-patch`

Inspects PostgreSQL patch series, guides source-aware correctness review, scaffolds functional SQL/TAP/isolation validation and controlled performance experiments, stores evidence-backed findings in SQLite, and recalls related history.

```bash
npx skills add https://github.com/pghacking/postgres-hacker-skills --skill review-pg-patch
```

## Usage

After installation, ask naturally. A compatible agent selects the relevant skill from your request; you do not need to name or pin a skill:

```text
Summarize the pgsql-hackers thread "Fix small psql slash option leaks".
```

```text
Find the pgsql-hackers discussion for this Message-ID and tell me whether its patch was committed or backpatched.
```

```text
Review this PostgreSQL patch, check related historical discussions, and design appropriate validation tests.
```

A full review request may use both skills automatically: `search-pg-hackers` retrieves the discussion and patch sets, then `review-pg-patch` inspects the source, recalls historical findings, and plans validation.

Mention `$search-pg-hackers` or `$review-pg-patch` only when you want to force a particular skill, debug skill selection, or make an automated workflow more explicit. This is optional for normal use.

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
