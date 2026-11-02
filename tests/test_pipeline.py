"""Offline integration tests; all workbook observations are fictional."""
from __future__ import annotations

from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from generate_workbook import build_workbook
from housing_radar import pipeline
from housing_radar.pipeline import run_pipeline


class HousingPipelineAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.data_dir = self.work / "data"
        self.workbook = build_workbook(self.work / "september.xlsx")

    def load(self, *, path=None, period="2026-09", published="2026-10-30", edition=1):
        return run_pipeline(self.data_dir, file_path=path or self.workbook,
                            release_period=period, published_at=published, edition=edition)

    def rows(self, sql, parameters=()):
        with closing(sqlite3.connect(self.data_dir / "warehouse.sqlite")) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(sql, parameters)]

    def scalar(self, sql, parameters=()):
        return next(iter(self.rows(sql, parameters)[0].values()))

    def trusted_observations(self):
        return self.rows("SELECT * FROM observations ORDER BY snapshot_id,series_id,month")

    def mutate(self, path, callback):
        workbook = load_workbook(path)
        try:
            callback(workbook["Data1"])
            workbook.save(path)
        finally:
            workbook.close()

    def assert_rejected_without_mutation(self, path, original, **kwargs):
        with self.assertRaises((ValueError, RuntimeError)):
            self.load(path=path, **kwargs)
        self.assertEqual(self.trusted_observations(), original)
        self.assertGreaterEqual(self.scalar("SELECT COUNT(*) FROM pipeline_runs WHERE status='failed'"), 1)

    def test_generated_workbook_is_reproducible_and_loads_complete_series(self):
        same = build_workbook(self.work / "same.xlsx")
        self.assertEqual(self.workbook.read_bytes(), same.read_bytes())
        summary = self.load()
        self.assertIsInstance(summary, dict)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM series"), 27)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM observations"), 24 * 27)
        self.assertEqual(self.scalar("SELECT COUNT(DISTINCT month) FROM current_observations"), 24)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM quality_findings"), 0)
        self.assertEqual(self.scalar("SELECT value FROM current_observations WHERE series_id='A422064L' AND month='2026-09-01'"), 2172)

    def test_same_bytes_replay_does_not_duplicate_vintage_or_observations(self):
        self.load()
        original = self.trusted_observations()
        copied = self.work / "copied.xlsx"
        shutil.copyfile(self.workbook, copied)
        self.load(path=copied)
        self.assertEqual(self.trusted_observations(), original)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM pipeline_runs WHERE status='success'"), 2)

    def test_same_vintage_with_changed_bytes_is_rejected(self):
        self.load()
        original = self.trusted_observations()
        changed = build_workbook(self.work / "changed.xlsx", adjustments={("2025-12", "NSW"): 5})
        self.assertNotEqual(self.workbook.read_bytes(), changed.read_bytes())
        self.assert_rejected_without_mutation(changed, original)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 1)

    def test_explicit_second_edition_preserves_original_and_records_revisions(self):
        self.load()
        original_id = self.scalar("SELECT snapshot_id FROM snapshots")
        original = self.trusted_observations()
        changed = build_workbook(self.work / "changed.xlsx", adjustments={("2025-12", "NSW"): 5})
        self.load(path=changed, edition=2, published="2026-10-31")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM observations"), 2 * 24 * 27)
        preserved = self.rows("SELECT * FROM observations WHERE snapshot_id=? ORDER BY snapshot_id,series_id,month", (original_id,))
        self.assertEqual(preserved, original)
        latest = self.scalar("SELECT DISTINCT snapshot_id FROM current_observations")
        self.assertNotEqual(latest, original_id)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=? AND change_type='changed'", (latest,)), 4)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=? AND change_type='new_observation'", (latest,)), 0)
        revision = self.rows("SELECT previous_value,change_value FROM release_changes WHERE snapshot_id=? AND series_id='A418511A' AND month='2025-12-01'", (latest,))[0]
        self.assertEqual(revision["change_value"], 5)

    def test_late_backfill_does_not_become_latest_and_new_month_is_not_revision(self):
        self.load()
        september_id = self.scalar("SELECT snapshot_id FROM snapshots")
        august = build_workbook(self.work / "august.xlsx", end="2026-08", months=23)
        self.load(path=august, period="2026-08", published="2026-10-01")
        self.assertEqual(self.scalar("SELECT DISTINCT snapshot_id FROM current_observations"), september_id)
        self.assertEqual(self.scalar("SELECT MAX(month) FROM current_observations"), "2026-09-01")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=? AND change_type='new_observation'", (september_id,)), 27)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=? AND change_type='changed'", (september_id,)), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=? AND change_type='unchanged'", (september_id,)), 23 * 27)

    def test_shortened_history_reports_removed_values_without_inventing_zeroes(self):
        august = build_workbook(self.work / "august-longer-start.xlsx", end="2026-08", months=24)
        self.load(path=august, period="2026-08", published="2026-10-01")
        report = self.load()
        latest = self.scalar("SELECT DISTINCT snapshot_id FROM current_observations")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM current_observations"), 648)
        self.assertEqual(self.scalar("SELECT MIN(month) FROM current_observations"), "2024-10-01")
        self.assertEqual(report["revision_summary"]["removed_observation"], 27)
        self.assertEqual(report["revision_summary"]["new_observation"], 27)
        self.assertEqual(report["revision_summary"]["unchanged"], 621)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM release_changes WHERE snapshot_id=?", (latest,)), 675)
        removed = self.rows("SELECT value,previous_value,change_value,change_type FROM release_changes WHERE snapshot_id=? AND series_id='A422064L' AND month='2024-09-01'", (latest,))[0]
        self.assertEqual(removed["change_type"], "removed_observation")
        self.assertIsNone(removed["value"])
        self.assertEqual(removed["previous_value"], 1596)
        self.assertIsNone(removed["change_value"])
        pointer = json.loads((self.data_dir / "exports" / "latest.json").read_text())
        with (self.data_dir / "exports" / pointer["directory"] / "release_changes.csv").open(newline="", encoding="utf-8") as stream:
            exported = list(csv.DictReader(stream))
        self.assertEqual(len(exported), 675)
        exported_removed = [row for row in exported if row["change_type"] == "removed_observation"]
        self.assertEqual(len(exported_removed), 27)
        self.assertTrue(all(row["value"] == "" and row["change_value"] == "" for row in exported_removed))

    def test_header_and_series_metadata_contracts_are_strict(self):
        self.load()
        original = self.trusted_observations()
        cases = {
            "unit": ("B2", "Dwellings"),
            "series_type": ("B3", "Seasonally Adjusted"),
            "data_type": ("B4", "STOCK"),
            "frequency": ("B5", "Quarter"),
            "collection_month_type": ("B6", "1"),
            "count_boolean": ("B9", True),
            "observation_count": ("B9", 23),
            "unknown_identifier": ("B10", "SYNTHETIC_UNKNOWN"),
            "duplicate_identifier": ("C10", "A418511A"),
            "description_mismatch": ("B1", "Total number of dwelling units ;  Houses ;  Victoria ;"),
            "metadata_row_label": ("A2", "Unrecognized units"),
        }
        for name, (cell, value) in cases.items():
            with self.subTest(contract=name):
                path = build_workbook(self.work / f"{name}.xlsx")
                self.mutate(path, lambda sheet: setattr(sheet[cell], "value", value))
                self.assert_rejected_without_mutation(path, original, edition=2, published="2026-10-31")

    def test_values_must_be_present_nonnegative_integers(self):
        self.load()
        original = self.trusted_observations()
        for index, value in enumerate((-1, 1.5, "not available", True, None, float("inf"))):
            with self.subTest(value=value):
                path = build_workbook(self.work / f"invalid-{index}.xlsx")
                self.mutate(path, lambda sheet: setattr(sheet["B11"], "value", value))
                self.assert_rejected_without_mutation(path, original, edition=2, published="2026-10-31")

    def test_missing_series_column_is_rejected(self):
        self.load()
        original = self.trusted_observations()
        malformed = build_workbook(self.work / "missing-series.xlsx")
        self.mutate(malformed, lambda sheet: sheet.delete_cols(2))
        self.assert_rejected_without_mutation(malformed, original, edition=2, published="2026-10-31")

    def test_duplicate_month_is_rejected(self):
        self.load()
        original = self.trusted_observations()
        malformed = build_workbook(self.work / "duplicate-month.xlsx")
        self.mutate(malformed, lambda sheet: setattr(sheet["A12"], "value", sheet["A11"].value))
        self.assert_rejected_without_mutation(malformed, original, edition=2, published="2026-10-31")

    def test_missing_month_is_rejected_even_when_count_metadata_is_adjusted(self):
        self.load()
        original = self.trusted_observations()
        malformed = build_workbook(self.work / "month-gap.xlsx")
        def remove_month(sheet):
            sheet.delete_rows(15)
            for column in range(2, 29):
                sheet.cell(9, column, 23)
        self.mutate(malformed, remove_month)
        self.assert_rejected_without_mutation(malformed, original, edition=2, published="2026-10-31")

    def test_latest_month_must_match_release_period(self):
        self.load()
        original = self.trusted_observations()
        self.assert_rejected_without_mutation(self.workbook, original, period="2026-10", published="2026-11-30")

    def test_truncated_workbook_is_rejected_with_raw_evidence_and_failure_audit(self):
        self.load()
        original = self.trusted_observations()
        truncated = self.work / "truncated.xlsx"
        truncated.write_bytes(self.workbook.read_bytes()[:100])
        self.assert_rejected_without_mutation(truncated, original, edition=2, published="2026-10-31")
        retained = self.rows("SELECT raw_path FROM source_artifacts")
        self.assertTrue(any(Path(item["raw_path"]).read_bytes() == truncated.read_bytes() for item in retained))

    def test_missing_data_sheet_is_rejected(self):
        self.load()
        original = self.trusted_observations()
        malformed = build_workbook(self.work / "missing-data-sheet.xlsx")
        workbook = load_workbook(malformed)
        workbook["Data1"].title = "WrongSheet"
        workbook.save(malformed)
        workbook.close()
        self.assert_rejected_without_mutation(malformed, original, edition=2, published="2026-10-31")

    def test_reconciliation_anomalies_are_preserved_as_nonblocking_findings(self):
        self.mutate(self.workbook, lambda sheet: setattr(sheet["B11"], "value", 101))
        self.load()
        self.assertEqual(self.scalar("SELECT value FROM observations WHERE series_id='A418511A' AND month='2024-10-01'"), 101)
        self.assertEqual(self.scalar("SELECT value FROM observations WHERE series_id='A422166A' AND month='2024-10-01'"), 150)
        findings = self.rows("SELECT expected,actual,delta FROM quality_findings WHERE month='2024-10-01'")
        self.assertEqual(len(findings), 2)
        self.assertTrue(all(row["expected"] - row["actual"] in (-1, 1) for row in findings))
        self.assertTrue(all(abs(row["delta"]) == 1 for row in findings))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM pipeline_runs WHERE status='success'"), 1)

    def test_trailing_twelve_requires_twelve_months_and_preserves_exact_total(self):
        self.load()
        metrics = self.rows("SELECT month,trailing_12_month_total,prior_year_value,yoy_pct FROM monthly_metrics WHERE series_id='A422064L' ORDER BY month")
        self.assertEqual(len(metrics), 24)
        self.assertTrue(all(row["trailing_12_month_total"] is None for row in metrics[:11]))
        self.assertEqual(metrics[11]["trailing_12_month_total"], 21024)
        self.assertEqual(metrics[-1]["trailing_12_month_total"], 24480)
        self.assertTrue(all(row["yoy_pct"] is None for row in metrics[:12]))
        self.assertEqual(metrics[-1]["prior_year_value"], 1884)
        self.assertAlmostEqual(metrics[-1]["yoy_pct"], (2172 / 1884 - 1) * 100, places=6)

    def test_zero_prior_year_baseline_has_null_percentage(self):
        zero = build_workbook(self.work / "zero-baseline.xlsx", zero_months={"2025-09"})
        self.load(path=zero)
        point = self.rows("SELECT value,prior_year_value,yoy_pct FROM monthly_metrics WHERE series_id='A422064L' AND month='2026-09-01'")[0]
        self.assertEqual(point["value"], 2172)
        self.assertEqual(point["prior_year_value"], 0)
        self.assertIsNone(point["yoy_pct"])

    def test_mid_insert_failure_rolls_back_entire_new_snapshot(self):
        self.load()
        original = self.trusted_observations()
        original_id = self.scalar("SELECT snapshot_id FROM snapshots")
        changed = build_workbook(self.work / "changed.xlsx", adjustments={("2025-12", "NSW"): 5})
        with closing(sqlite3.connect(self.data_dir / "warehouse.sqlite")) as connection:
            connection.execute(f"""CREATE TRIGGER inject_observation_failure BEFORE INSERT ON observations
                WHEN NEW.snapshot_id <> {int(original_id)}
                     AND (SELECT COUNT(*) FROM observations WHERE snapshot_id=NEW.snapshot_id) >= 10
                BEGIN SELECT RAISE(ABORT, 'Injected mid-insert failure'); END""")
            connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.load(path=changed, edition=2, published="2026-10-31")
        self.assertEqual(self.trusted_observations(), original)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM series"), 27)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM pipeline_runs WHERE status='failed'"), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM source_artifacts"), 2)
        with closing(sqlite3.connect(self.data_dir / "warehouse.sqlite")) as connection:
            connection.execute("DROP TRIGGER inject_observation_failure")
            connection.commit()
        self.load(path=changed, edition=2, published="2026-10-31")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM observations"), 1296)

    def test_csv_and_json_exports_match_the_trusted_snapshot(self):
        self.mutate(self.workbook, lambda sheet: setattr(sheet["B11"], "value", 101))
        report = self.load()
        exports = self.data_dir / "exports"
        pointer = json.loads((exports / "latest.json").read_text())
        self.assertEqual(pointer["run_id"], report["run_id"])
        generation = exports / pointer["directory"]
        saved_report = json.loads((exports / pointer["report"]).read_text())
        self.assertEqual(saved_report, report)
        self.assertEqual(saved_report["current_rows"], 648)
        self.assertEqual(saved_report["quality_findings_count"], 2)
        queries = {
            "monthly_metrics.csv": "SELECT * FROM monthly_metrics ORDER BY month,series_id",
            "release_changes.csv": "SELECT * FROM release_changes ORDER BY month,series_id",
            "quality_findings.csv": "SELECT rule,month,region,dwelling_type,expected,actual,delta FROM quality_findings ORDER BY month,rule,region,dwelling_type",
        }
        for filename, query in queries.items():
            with self.subTest(export=filename):
                with (generation / filename).open(newline="", encoding="utf-8") as stream:
                    exported = list(csv.DictReader(stream))
                expected = [{key: "" if value is None else str(value) for key, value in row.items()} for row in self.rows(query)]
                self.assertEqual(exported, expected)

    def test_failed_export_retains_snapshot_and_previous_pointer_then_replay_recovers(self):
        self.load()
        pointer_file = self.data_dir / "exports" / "latest.json"
        prior_pointer = pointer_file.read_text()
        changed = build_workbook(self.work / "changed.xlsx", adjustments={("2025-12", "NSW"): 5})

        def fail_after_partial_export(connection, directory, report):
            generation = directory / report["run_id"]
            generation.mkdir(parents=True)
            (generation / "monthly_metrics.csv").write_text("simulated partial export\n")
            raise OSError("Injected export failure")

        with patch.object(pipeline, "_export", side_effect=fail_after_partial_export):
            with self.assertRaisesRegex(OSError, "Injected export failure"):
                self.load(path=changed, edition=2, published="2026-10-31")
        self.assertEqual(pointer_file.read_text(), prior_pointer)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM observations"), 1296)
        failure = self.rows("SELECT snapshot_id,error FROM pipeline_runs WHERE status='failed'")[0]
        self.assertIsNotNone(failure["snapshot_id"])
        self.assertIn("Snapshot committed; report failed", failure["error"])
        replay = self.load(path=changed, edition=2, published="2026-10-31")
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM snapshots"), 2)
        self.assertNotEqual(pointer_file.read_text(), prior_pointer)
        pointer = json.loads(pointer_file.read_text())
        saved = json.loads((self.data_dir / "exports" / pointer["report"]).read_text())
        self.assertEqual(saved["current_edition"], 2)
        self.assertEqual(saved["current_rows"], 648)

    def test_report_generation_keeps_one_read_snapshot_during_another_commit(self):
        self.load()
        original_export = pipeline._export
        changed = build_workbook(self.work / "changed.xlsx", adjustments={("2025-12", "NSW"): 5})

        def commit_new_edition_then_export(connection, directory, report):
            # A second connection commits after report.json's contents were read.
            # All CSV reads for the first generation must remain on edition 1.
            with patch.object(pipeline, "_export", wraps=original_export):
                self.load(path=changed, edition=2)
            original_export(connection, directory, report)

        with patch.object(pipeline, "_export", side_effect=commit_new_edition_then_export):
            report = pipeline.export_report(self.data_dir)
        self.assertEqual(report["current_edition"], 1)
        generation = self.data_dir / "exports" / report["run_id"]
        with (generation / "monthly_metrics.csv").open(newline="") as stream:
            exported = list(csv.DictReader(stream))
        self.assertEqual({row["edition"] for row in exported}, {"1"})
        self.assertEqual(self.scalar("SELECT MAX(edition) FROM snapshots"), 2)
        # The pointer can still finish out of order across concurrent runners.
        # Production orchestration must serialize access to a data directory.

    def test_source_provenance_and_database_integrity(self):
        self.load()
        artifact = self.rows("SELECT * FROM source_artifacts")[0]
        raw = Path(artifact["raw_path"]).read_bytes()
        self.assertEqual(raw, self.workbook.read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), artifact["sha256"])
        self.assertEqual(self.scalar("PRAGMA integrity_check"), "ok")
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])


if __name__ == "__main__":
    unittest.main()
