import os
import shutil
import tempfile
import unittest
from datetime import date

import trakt_rewind as tr


class TestTraktRewind(unittest.TestCase):
    def setUp(self):
        self._orig_cfg = dict(tr.APP_CONFIG)
        self._orig_sched = dict(tr.APP_CONFIG["schedule"])
        self._orig_cache_file = tr.CACHE_FILE
        self._orig_backup_dir = tr.BACKUP_DIR
        self._tmpdir = tempfile.mkdtemp(prefix="trakt_rewind_test_")
        tr.CACHE_FILE = os.path.join(self._tmpdir, "trakt_cache.json")
        tr.BACKUP_DIR = os.path.join(self._tmpdir, "trakt_backups")
        tr.APP_CONFIG["timezone_offset_minutes"] = 330
        tr.APP_CONFIG["timezone_label"] = "IST"
        tr.APP_CONFIG["timestamp_style"] = "spread"
        tr.APP_CONFIG["cache_enabled"] = True
        tr.APP_CONFIG["schedule"] = {
            "default_window": ["07:00", "22:00"],
            "weekday_busy_cutoff_date": "2025-04-30",
            "weekday_windows_before_cutoff": [["06:00", "07:00"], ["14:00", "22:00"]],
        }
        tr.random.seed(42)

    def tearDown(self):
        tr.APP_CONFIG.clear()
        tr.APP_CONFIG.update(self._orig_cfg)
        tr.APP_CONFIG["schedule"] = self._orig_sched
        tr.CACHE_FILE = self._orig_cache_file
        tr.BACKUP_DIR = self._orig_backup_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_no_hardcoded_client_id(self):
        self.assertEqual(tr.DEFAULT_CLIENT_ID, "")

    def test_runtime_no_overlap_on_heavy_weekday(self):
        # 15 x 42-43m drama episodes on a weekday before cutoff
        runtimes = [42, 43, 42, 42, 43, 42, 42, 43, 42, 43, 42, 42, 43, 42, 42]
        warnings = []
        ts = tr.generate_day_timestamps(
            date(2022, 12, 6), 15, runtime_min=42, ep_runtimes=runtimes, warnings_out=warnings
        )
        self.assertEqual(len(ts), 15)
        self.assertTrue(len(warnings) >= 1)
        for i in range(1, len(ts)):
            diff_min = (ts[i] - ts[i - 1]).total_seconds() / 60.0
            self.assertGreaterEqual(diff_min, runtimes[i - 1])

    def test_weekday_busy_hours_respected_when_fits(self):
        runtimes = [42, 43, 42, 42, 43]
        warnings = []
        ts = tr.generate_day_timestamps(
            date(2022, 12, 6), 5, runtime_min=42, ep_runtimes=runtimes, warnings_out=warnings
        )
        self.assertEqual(len(ts), 5)
        self.assertEqual(warnings, [])
        for t, rt in zip(ts, runtimes):
            start_m = t.hour * 60 + t.minute
            end_m = start_m + rt
            if start_m < 7 * 60:
                self.assertLessEqual(end_m, 7 * 60)
            else:
                self.assertGreaterEqual(start_m, 14 * 60)
                self.assertLessEqual(end_m, 22 * 60)

    def test_custom_start_time_honored(self):
        runtimes = [42, 43, 42]
        ts = tr.generate_day_timestamps(
            date(2022, 11, 30), 3, runtime_min=42, start_time_str="13:22", ep_runtimes=runtimes
        )
        self.assertEqual(ts[0].hour, 13)
        self.assertEqual(ts[0].minute, 22)
        for i in range(1, len(ts)):
            diff_min = (ts[i] - ts[i - 1]).total_seconds() / 60.0
            self.assertGreaterEqual(diff_min, runtimes[i - 1])

    def test_gap_and_binge_styles(self):
        for style in ("gap", "binge"):
            tr.APP_CONFIG["timestamp_style"] = style
            ts = tr.generate_day_timestamps(date(2025, 7, 10), 4, runtime_min=24)
            self.assertEqual(len(ts), 4)
            for i in range(1, len(ts)):
                diff_min = (ts[i] - ts[i - 1]).total_seconds() / 60.0
                self.assertGreaterEqual(diff_min, 24.0)

    def test_range_parser(self):
        mock_eps = [
            {"season": 1, "number": i, "title": f"Ep {i}"} for i in range(1, 13)
        ] + [
            {"season": 2, "number": i, "title": f"S2 Ep {i}"} for i in range(1, 11)
        ]
        self.assertEqual(tr.parse_range_expression("1-3", mock_eps), (1, 3, None))
        self.assertEqual(tr.parse_range_expression("1 - 3", mock_eps), (1, 3, None))
        self.assertEqual(tr.parse_range_expression("1 to 5", mock_eps), (1, 5, None))
        self.assertEqual(tr.parse_range_expression("S02E01-S02E05", mock_eps), (13, 17, None))
        self.assertEqual(tr.parse_range_expression("2x1 - 2x4", mock_eps), (13, 16, None))
        self.assertEqual(tr.parse_range_expression("season 2", mock_eps), (13, 22, None))
        self.assertEqual(tr.parse_range_expression("all", mock_eps), (1, 22, None))
        s, e, err = tr.parse_range_expression("1-99", mock_eps)
        self.assertIsNone(s)
        self.assertIn("Out of range", err)

    def test_flexible_date_parser(self):
        self.assertEqual(tr.parse_flexible_date("2022-11-30"), date(2022, 11, 30))
        self.assertEqual(tr.parse_flexible_date("2022/11/30"), date(2022, 11, 30))
        self.assertEqual(tr.parse_flexible_date("30-11-2022"), date(2022, 11, 30))
        with self.assertRaises(ValueError):
            tr.parse_flexible_date("not-a-date")

    def test_release_date_and_future_airdate(self):
        rec = {"use_released": True, "new_dt": None}
        self.assertEqual(tr.build_watched_at_value(rec), "released")
        self.assertFalse(tr.is_future_airdate("2024-04-06T14:30:00.000Z"))
        self.assertTrue(tr.is_future_airdate("2099-01-01T00:00:00.000Z"))

    def test_disk_cache_roundtrip(self):
        c = tr.empty_cache()
        c["watched"][18083] = {"plays": 22, "watched_eps": 22, "exact_hydrated": True}
        c["ratings"][18083] = {"rating": 10}
        c["watchlist"].add(999)
        c["favorites"].add(18083)
        c["custom_lists"][18083] = ["Favorites"]
        tr.save_cache_to_disk(c)

        reloaded = tr.load_cache_from_disk()
        self.assertIsNotNone(reloaded)
        self.assertIn(18083, reloaded["watched"])
        self.assertEqual(reloaded["ratings"][18083]["rating"], 10)
        self.assertIsInstance(reloaded["watchlist"], set)
        self.assertIn(999, reloaded["watchlist"])
        self.assertEqual(reloaded["custom_lists"][18083], ["Favorites"])

    def test_local_snapshot_backup(self):
        mock_show = {
            "title": "The Vampire Diaries",
            "year": 2009,
            "ids": {"trakt": 18083},
            "status": "ended",
            "aired_episodes": 171,
            "runtime": 42,
        }
        mock_hist = [
            {"id": 111, "watched_at": "2022-11-25T14:57:00.000Z", "episode": {"season": 1, "number": 1, "ids": {"trakt": 5001}}}
        ]
        mock_cache = {"ratings": {18083: {"rating": 10}}}
        fpath = tr.save_show_snapshot(mock_show, mock_hist, mock_cache, reason="test")
        self.assertTrue(os.path.exists(fpath))
        metas = tr.list_local_snapshots()
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["type"], "show")


if __name__ == "__main__":
    unittest.main()
