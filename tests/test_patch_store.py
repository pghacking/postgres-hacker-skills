import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).parent
SCRIPT = HERE / "search-pg-hackers/scripts/postgresql_archive.py"
if not SCRIPT.exists():
    SCRIPT = HERE.parent / "skills/search-pg-hackers/scripts/postgresql_archive.py"
SPEC = importlib.util.spec_from_file_location("postgresql_archive", SCRIPT)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


def result(attachments, message_id="patch-v1@example.test", date="2026-01-01 12:00:00"):
    return {
        "thread_url": "https://www.postgresql.org/message-id/flat/root",
        "messages": [
            {
                "message_id": message_id,
                "url": f"https://www.postgresql.org/message-id/{message_id}",
                "date": date,
                "subject": "[PATCH v1] example",
                "attachments": attachments,
            }
        ],
    }


class PatchStoreTest(unittest.TestCase):
    def test_resync_and_review_never_redownload_known_set(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return b"patch payload\n"

        original = [{"name": "v1.patch", "url": "https://example.test/v1.patch"}]
        with tempfile.TemporaryDirectory() as temporary, patch.object(archive, "fetch", fake_fetch):
            store = Path(temporary)
            first = archive.sync_patch_sets(result(original), store)
            self.assertEqual(first["downloaded_attachments"], 1)
            self.assertEqual(len(calls), 1)

            second = archive.sync_patch_sets(result(original), store)
            self.assertEqual(second["downloaded_attachments"], 0)
            self.assertEqual(len(calls), 1)

            manifest = json.loads((store / "manifest.json").read_text())
            patch_set = manifest["patch_sets"][0]
            self.assertTrue((store / patch_set["attachments"][0]["patch_set_path"]).exists())
            archive.mark_reviewed(store, patch_set["id"])

            changed = original + [
                {"name": "late.patch", "url": "https://example.test/late.patch"}
            ]
            third = archive.sync_patch_sets(result(changed), store)
            self.assertEqual(third["skipped_reviewed_patch_sets"], 1)
            self.assertEqual(len(calls), 1)

    def test_patch_sets_are_independent_but_share_known_objects(self):
        attachment = {"name": "series.patch", "url": "https://example.test/series.patch"}
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            archive, "fetch", return_value=b"same payload\n"
        ) as mocked:
            store = Path(temporary)
            archive.sync_patch_sets(result([attachment]), store)
            archive.sync_patch_sets(
                result([attachment], message_id="patch-v2@example.test", date="2026-01-02 12:00:00"),
                store,
            )
            manifest = json.loads((store / "manifest.json").read_text())
            self.assertEqual(len(manifest["patch_sets"]), 2)
            self.assertEqual(mocked.call_count, 1)
            paths = [store / item["attachments"][0]["patch_set_path"] for item in manifest["patch_sets"]]
            self.assertNotEqual(paths[0].parent, paths[1].parent)
            self.assertTrue(all(path.exists() for path in paths))


if __name__ == "__main__":
    unittest.main()
