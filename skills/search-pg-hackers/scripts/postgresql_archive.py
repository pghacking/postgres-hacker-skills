#!/usr/bin/env python3
"""Search and retrieve PostgreSQL mailing-list threads from the official archive."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, unquote
from urllib.request import Request, urlopen

BASE_URL = "https://www.postgresql.org"
USER_AGENT = "postgres-hacker-skills/1.0 (+https://github.com/pghacking/postgres-hacker-skills)"


def fetch(url: str, attempts: int = 3) -> bytes:
    error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def clean_html(fragment: str) -> str:
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?i)</p\s*>", "\n\n", fragment)
    fragment = re.sub(r"(?i)</(?:div|li|tr|h[1-6])\s*>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(fragment).replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def canonical_message_id(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and "/message-id/" in parsed.path:
        value = parsed.path.split("/message-id/", 1)[1]
        for prefix in ("flat/", "raw/", "mbox/"):
            if value.startswith(prefix):
                value = value[len(prefix) :]
        value = value.split("/", 1)[0]
    return unquote(value).strip().strip("<>")


def message_url(message_id: str, flat: bool = False) -> str:
    encoded = quote(canonical_message_id(message_id), safe="")
    part = "message-id/flat" if flat else "message-id"
    return f"{BASE_URL}/{part}/{encoded}"


def search(query: str, list_name: str, limit: int) -> dict:
    params = urlencode({"q": query, "ln": list_name, "m": "1"})
    url = f"{BASE_URL}/search/?{params}"
    page = fetch(url).decode("utf-8", "replace")
    pattern = re.compile(
        r'\b\d+\.\s*<a href="(https://www\.postgresql\.org/message-id/[^\"]+)">(.*?)</a>'
        r'.{0,400}?From\s+(.*?)\s+on\s+([^<]+)\.<br\s*/?>',
        re.DOTALL,
    )
    results = []
    seen = set()
    for match in pattern.finditer(page):
        result_url, subject, author, date = match.groups()
        message_id = canonical_message_id(result_url)
        if message_id in seen:
            continue
        seen.add(message_id)
        results.append(
            {
                "subject": clean_html(subject),
                "author": clean_html(author),
                "date": clean_html(date),
                "message_id": message_id,
                "url": result_url,
            }
        )
        if len(results) >= limit:
            break
    return {
        "query": query,
        "list": list_name,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "search_url": url,
        "results": results,
    }


def field(block: str, name: str) -> str | None:
    match = re.search(
        rf"<th[^>]*>\s*{re.escape(name)}:\s*</th>\s*<td[^>]*>(.*?)</td>",
        block,
        re.DOTALL | re.IGNORECASE,
    )
    return clean_html(match.group(1)) if match else None


def parse_thread(page: str, source_id: str) -> dict:
    table_marker = re.compile(r'<table[^>]*class="[^"]*message-header[^"]*"[^>]*>', re.I)
    starts = [match.start() for match in table_marker.finditer(page)]
    messages = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page)
        block = page[start:end]
        mid = field(block, "Message-ID")
        if not mid:
            continue
        content_match = re.search(
            r'<div class="message-content">(.*?)</div>', block, re.DOTALL | re.IGNORECASE
        )
        attachments = []
        for href, label in re.findall(
            r'<a href="([^"]*/message-id/attachment/[^"]+)">(.*?)</a>', block, re.DOTALL
        ):
            attachments.append(
                {"name": clean_html(label), "url": urljoin(BASE_URL, html.unescape(href))}
            )
        messages.append(
            {
                "message_id": mid,
                "from": field(block, "From"),
                "to": field(block, "To"),
                "subject": field(block, "Subject"),
                "date": field(block, "Date"),
                "lists": field(block, "Lists"),
                "url": message_url(mid),
                "body": clean_html(content_match.group(1)) if content_match else "",
                "attachments": attachments,
            }
        )
    return {
        "source_message_id": source_id,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "thread_url": message_url(source_id, flat=True),
        "message_count": len(messages),
        "messages": messages,
    }


def safe_filename(name: str) -> str:
    name = Path(name).name.replace("\x00", "")
    return name or "attachment"


def patch_set_id(message: dict) -> str:
    digest = hashlib.sha256(message["message_id"].encode()).hexdigest()[:12]
    date = re.sub(r"[^0-9]", "", message.get("date") or "")[:14] or "undated"
    return f"{date}-{digest}"


def load_manifest(store: Path) -> dict:
    path = store / "manifest.json"
    if not path.exists():
        return {"schema_version": 1, "patch_sets": []}
    with path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("patch_sets"), list):
        raise RuntimeError(f"unsupported patch manifest: {path}")
    return manifest


def save_manifest(store: Path, manifest: dict) -> None:
    path = store / "manifest.json"
    temporary = store / ".manifest.json.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    temporary.replace(path)


def materialize(source: Path, target: Path) -> None:
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def sync_patch_sets(result: dict, store: Path) -> dict:
    store.mkdir(parents=True, exist_ok=True)
    objects = store / "objects"
    sets_dir = store / "patch-sets"
    objects.mkdir(exist_ok=True)
    sets_dir.mkdir(exist_ok=True)
    manifest = load_manifest(store)
    manifest["thread_url"] = result["thread_url"]
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    by_id = {item["id"]: item for item in manifest["patch_sets"]}
    known_urls = {
        attachment["url"]: attachment
        for patch_set in manifest["patch_sets"]
        for attachment in patch_set.get("attachments", [])
    }
    downloaded = 0
    new_objects = 0
    reused = 0
    skipped_reviewed = 0

    for message in result["messages"]:
        if not message["attachments"]:
            continue
        set_id = patch_set_id(message)
        patch_set = by_id.get(set_id)
        if patch_set is None:
            patch_set = {
                "id": set_id,
                "message_id": message["message_id"],
                "message_url": message["url"],
                "date": message["date"],
                "subject": message["subject"],
                "status": "pending",
                "attachments": [],
            }
            manifest["patch_sets"].append(patch_set)
            by_id[set_id] = patch_set
        if patch_set.get("status") == "reviewed":
            skipped_reviewed += 1
            continue

        set_dir = sets_dir / set_id
        set_dir.mkdir(exist_ok=True)
        known = {item["url"]: item for item in patch_set["attachments"]}
        used_names = {item["stored_name"] for item in patch_set["attachments"]}
        for attachment in message["attachments"]:
            existing = known.get(attachment["url"])
            if existing:
                object_path = store / existing["object_path"]
                target = store / existing["patch_set_path"]
                if not object_path.exists():
                    raise RuntimeError(f"manifest object is missing: {object_path}")
                materialize(object_path, target)
                attachment.update(existing)
                reused += 1
                continue

            shared = known_urls.get(attachment["url"])
            if shared:
                digest = shared["sha256"]
                size = shared["size"]
                object_path = store / shared["object_path"]
                if not object_path.exists():
                    raise RuntimeError(f"manifest object is missing: {object_path}")
                reused += 1
            else:
                payload = fetch(attachment["url"])
                downloaded += 1
                size = len(payload)
                digest = hashlib.sha256(payload).hexdigest()
                object_path = objects / digest
                if not object_path.exists():
                    temporary = objects / f".{digest}.tmp"
                    temporary.write_bytes(payload)
                    temporary.replace(object_path)
                    new_objects += 1
                else:
                    reused += 1
            name = safe_filename(attachment["name"])
            candidate = name
            counter = 2
            while candidate in used_names:
                candidate = f"{Path(name).stem}-{counter}{Path(name).suffix}"
                counter += 1
            used_names.add(candidate)
            target = set_dir / candidate
            materialize(object_path, target)
            record = {
                "name": attachment["name"],
                "stored_name": candidate,
                "url": attachment["url"],
                "sha256": digest,
                "size": size,
                "object_path": str(object_path.relative_to(store)),
                "patch_set_path": str(target.relative_to(store)),
            }
            patch_set["attachments"].append(record)
            known_urls[attachment["url"]] = record
            attachment.update(record)

    manifest["patch_sets"].sort(key=lambda item: (item.get("date") or "", item["id"]))
    save_manifest(store, manifest)
    return {
        "store": str(store.resolve()),
        "manifest": str((store / "manifest.json").resolve()),
        "patch_set_count": len(manifest["patch_sets"]),
        "downloaded_attachments": downloaded,
        "new_objects": new_objects,
        "reused_objects": reused,
        "skipped_reviewed_patch_sets": skipped_reviewed,
    }


def mark_reviewed(store: Path, set_id: str) -> dict:
    manifest = load_manifest(store)
    for patch_set in manifest["patch_sets"]:
        if patch_set["id"] == set_id:
            patch_set["status"] = "reviewed"
            patch_set["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            save_manifest(store, manifest)
            return patch_set
    raise RuntimeError(f"patch set not found: {set_id}")


def thread(value: str, patch_store: Path | None) -> dict:
    mid = canonical_message_id(value)
    page = fetch(message_url(mid, flat=True)).decode("utf-8", "replace")
    result = parse_thread(page, mid)
    if not result["messages"]:
        raise RuntimeError("archive page contained no parseable messages")
    if patch_store:
        result["patch_store"] = sync_patch_sets(result, patch_store)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    search_parser = subparsers.add_parser("search", help="search an official list archive")
    search_parser.add_argument("query")
    search_parser.add_argument("--list", default="pgsql-hackers", dest="list_name")
    search_parser.add_argument("--limit", type=int, default=20)
    thread_parser = subparsers.add_parser("thread", help="retrieve a whole thread")
    thread_parser.add_argument("message_id", help="Message-ID or official message URL")
    thread_parser.add_argument("--patch-store", type=Path, metavar="DIR")
    reviewed_parser = subparsers.add_parser(
        "mark-reviewed", help="mark a stored patch set as reviewed"
    )
    reviewed_parser.add_argument("store", type=Path)
    reviewed_parser.add_argument("patch_set_id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "search":
            result = search(args.query, args.list_name, args.limit)
        elif args.command == "thread":
            result = thread(args.message_id, args.patch_store)
        else:
            result = mark_reviewed(args.store, args.patch_set_id)
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
