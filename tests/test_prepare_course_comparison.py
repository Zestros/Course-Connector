import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_course_comparison as prep


class PrepareCourseComparisonTests(unittest.TestCase):
    def test_rejects_raw_moodle_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "contents.json"
            raw_path.write_text(json.dumps({"id": 1, "modules": []}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                prep.load_normalized_course(raw_path)

    def test_builds_alignment_candidate_with_evidence(self):
        course_a = prep.load_normalized_course(ROOT / "tests/fixtures/min_course_a.course.normalized.json")
        course_b = prep.load_normalized_course(ROOT / "tests/fixtures/min_course_b.course.normalized.json")
        candidates = prep.build_alignment_candidates(course_a, course_b, min_score=0.01, max_candidates=10)
        self.assertGreaterEqual(len(candidates), 1)
        first = candidates[0]
        self.assertEqual(first["candidate_type"], "alignment_verification")
        self.assertGreater(len(first["evidence_refs"]), 0)
        self.assertIn(first["relation_hint"], {"reinforcement", "duplication", "uncertain"})


if __name__ == "__main__":
    unittest.main()
