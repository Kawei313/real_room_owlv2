import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import percentile, read_prompts, read_synonyms


class CommonTests(unittest.TestCase):
    def test_read_prompts_skips_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.txt"; path.write_text("# note\nchair\n\n desk \n", encoding="utf-8")
            self.assertEqual(read_prompts(path), ["chair", "desk"])

    def test_duplicate_prompts_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.txt"; path.write_text("chair\nchair\n", encoding="utf-8")
            with self.assertRaises(ValueError): read_prompts(path)

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], .5), 3)


if __name__ == "__main__":
    unittest.main()
