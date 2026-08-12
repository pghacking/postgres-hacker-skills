import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).parent
SCRIPT = HERE / "review-pg-patch/scripts/review_memory.py"
if not SCRIPT.exists():
    SCRIPT = HERE.parent / "skills/review-pg-patch/scripts/review_memory.py"
SPEC = importlib.util.spec_from_file_location("review_memory", SCRIPT)
memory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memory)


class ReviewMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = memory.connect(self.root / "memory.sqlite3")
        self.thread = {
            "thread_url": "https://www.postgresql.org/message-id/flat/root",
            "retrieved_at": "2026-01-02T00:00:00+00:00",
            "messages": [
                {
                    "message_id": "root@example.test",
                    "from": "Reviewer <reviewer@example.test>",
                    "date": "2026-01-01 00:00:00",
                    "subject": "[PATCH] Fix cleanup",
                    "url": "https://www.postgresql.org/message-id/root",
                    "body": "The error path leaks the parsed option.",
                }
            ],
        }
        self.manifest = {
            "thread_url": self.thread["thread_url"],
            "updated_at": "2026-01-02T00:00:00+00:00",
            "patch_sets": [
                {
                    "id": "patch-v1",
                    "message_id": "root@example.test",
                    "subject": "[PATCH] Fix cleanup",
                    "date": "2026-01-01 00:00:00",
                    "status": "reviewed",
                    "attachments": [{"sha256": "abc", "name": "v1.patch"}],
                }
            ],
        }
        (self.root / "thread.json").write_text(json.dumps(self.thread))
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        memory.ingest(self.db, self.root / "thread.json", self.root / "manifest.json")

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def finding_args(self):
        return argparse.Namespace(
            patch_set_id="patch-v1",
            category="resource-management",
            severity="warning",
            claim="The error path does not release the parsed option.",
            rationale="The parser returns malloc-owned memory.",
            disposition="open",
            confidence="high",
            created_by="test-agent",
            source_message_id="root@example.test",
            source_url="https://www.postgresql.org/message-id/root",
            source_ref=None,
            evidence="error path leaks the parsed option",
            file=["src/bin/psql/command.c"],
            symbol=["exec_command_example"],
            subsystem=["psql"],
            topic=["ownership"],
        )

    def test_ingest_remember_recall_and_update(self):
        finding = memory.remember(self.db, self.finding_args())
        self.assertEqual(finding["patch_set_id"], "patch-v1")
        self.assertEqual(finding["patch_set_sha256"], memory.hashlib.sha256(b"abc").hexdigest())

        recall_args = argparse.Namespace(
            thread_url=None,
            query="malloc owned memory",
            limit=10,
            file=["src/bin/psql/command.c"],
            symbol=["exec_command_example"],
            subsystem=[],
            topic=[],
        )
        recalled = memory.recall(self.db, recall_args)
        self.assertEqual(recalled["count"], 1)
        self.assertIn("symbol:exec_command_example", recalled["findings"][0]["recall_reasons"])

        update_args = argparse.Namespace(
            finding_id=finding["id"],
            disposition="fixed",
            superseded_by_finding_id=None,
            superseded_by_patch_set_id="patch-v1",
        )
        updated = memory.update_finding(self.db, update_args)
        self.assertEqual(updated["disposition"], "fixed")

    def test_requires_provenance(self):
        args = self.finding_args()
        args.source_message_id = None
        args.source_url = None
        with self.assertRaisesRegex(RuntimeError, "provide --source"):
            memory.remember(self.db, args)

    def test_ingest_is_idempotent(self):
        memory.ingest(self.db, self.root / "thread.json", self.root / "manifest.json")
        self.assertEqual(self.db.execute("SELECT count(*) FROM threads").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM messages").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM patch_sets").fetchone()[0], 1)

    def test_manifest_can_be_ingested_before_thread(self):
        other = memory.connect(self.root / "manifest-first.sqlite3")
        try:
            memory.ingest(other, None, self.root / "manifest.json")
            row = other.execute("SELECT id, message_id FROM patch_sets").fetchone()
            self.assertEqual(row["id"], "patch-v1")
            self.assertIsNone(row["message_id"])
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
