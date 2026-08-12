import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "skills/review-pg-patch/scripts/patch_review.py"
SPEC = importlib.util.spec_from_file_location("patch_review", SCRIPT)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


PATCH = """From abc Mon Sep 17 00:00:00 2001
Subject: [PATCH] Fix option cleanup
diff --git a/src/bin/psql/command.c b/src/bin/psql/command.c
--- a/src/bin/psql/command.c
+++ b/src/bin/psql/command.c
@@ -1,2 +1,3 @@
 old();
+free(option);
"""


class PatchReviewTest(unittest.TestCase):
    def test_inspect_and_generate_plans(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patches = root / "patches"
            source = root / "postgres"
            patches.mkdir()
            (source / "src/bin/psql").mkdir(parents=True)
            (source / "src/bin/psql/command.c").write_text("old();\n")
            (patches / "0001.patch").write_text(PATCH)

            inspection = review.inspect(patches, source)
            self.assertEqual(inspection["changed_files"], ["src/bin/psql/command.c"])
            self.assertIn("psql", inspection["suggested_subsystems"])
            self.assertIn("ownership-lifetime", inspection["suggested_risks"])
            self.assertEqual(inspection["patches"][0]["additions"], 1)
            self.assertEqual(inspection["patches"][0]["subject"], "[PATCH] Fix option cleanup")

            functional = root / "functional"
            performance = root / "performance"
            review.write_functional(functional, inspection)
            review.write_performance(performance, inspection)
            self.assertTrue((functional / "test.sql").exists())
            self.assertEqual(json.loads((functional / "plan.json").read_text())["kind"], "functional")
            self.assertTrue((performance / "run.sh").stat().st_mode & 0o100)
            self.assertEqual(json.loads((performance / "experiment.json").read_text())["kind"], "performance")

    def test_empty_patch_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "no patch files"):
                review.inspect(Path(temporary), None)


if __name__ == "__main__":
    unittest.main()
