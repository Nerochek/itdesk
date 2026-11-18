"""Проверки очистки и MapReduce стандартным unittest."""
import json
import unittest
from analytics.pipeline import clean_frame
from analytics.mapreduce.mapper import map_lines
from analytics.mapreduce.reducer import reduce_lines


class PipelineTests(unittest.TestCase):
    def test_cleaning_bad_ids_duplicates_missing_and_normalization(self):
        rows = [
            dict(source=" test ", source_id="1", title=" old ", status=" NEW "),
            dict(source="test", source_id=1, title=" final ", status=" CLOSED ", category="???"),
            dict(source="test", source_id="bad", title="bad"),
            dict(source="test", source_id=2.5, title="bad"),
            dict(source="test", source_id=2, title="   "),
            dict(source="test", source_id=3, title="valid", created_at="not a date"),
        ]
        frame, report = clean_frame(rows)
        self.assertEqual(report, dict(input_rows=6, output_rows=2, removed_rows=4))
        row = frame.loc[frame.source_id.eq(1)].iloc[0]
        self.assertEqual((row.title, row.status, row.category), ("final", "closed", "other"))
        self.assertIsNone(row.created_at)

    def test_empty_input(self):
        frame, _ = clean_frame([])
        self.assertTrue(frame.empty)

    def test_mapreduce_filters_and_sums(self):
        rows = [dict(category="network", status=s) for s in ("new", "resolved", "in_progress")]
        lines = [json.dumps(row) for row in rows]
        self.assertEqual(list(reduce_lines(sorted(map_lines(lines)))), ["network\t2\n"])

    def test_mapreduce_rejects_malformed_input(self):
        with self.assertRaises(json.JSONDecodeError):
            list(map_lines(["not json"]))


if __name__ == "__main__":
    unittest.main()
