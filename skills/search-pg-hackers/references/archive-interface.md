# PostgreSQL archive interface

The official archive base URL is `https://www.postgresql.org`.

## Endpoints

- Search: `/search/?q=<query>&ln=pgsql-hackers&m=1`
- Message: `/message-id/<url-encoded-message-id>`
- Whole thread: `/message-id/flat/<url-encoded-message-id>`
- Attachment: use the exact `/message-id/attachment/...` URL exposed by the message page

Always percent-encode the Message-ID as a single path component. Gmail Message-IDs commonly contain `+`, `=`, and `@`; treating `+` as a query-space produces false misses.

The archive HTML is the source of truth for message headers, bodies, response links, and attachments. Search-engine indexing can lag behind newly archived mail.

## Failure handling

- Retry transient HTTP failures with bounded exponential backoff.
- Send a descriptive User-Agent.
- Do not silently replace an official-archive failure with an unrelated search result.
- Preserve the canonical official URL in structured output.
- Treat attachment filenames as hostile: discard directory components before saving.

The bundled script uses only the Python standard library so an installed skill does not require package installation.

## Patch store

`thread --patch-store DIR` creates:

```text
DIR/
├── manifest.json
├── objects/<sha256>
└── patch-sets/<date-and-message-id-hash>/<attachment-name>
```

The manifest is authoritative for provenance and `pending`/`reviewed` status. Object files are content-addressed. Patch-set files are hard links when supported and copies otherwise. A known attachment URL is never fetched again on a normal resync; reviewed sets are skipped as a unit.
