"""Run with: python3 -m unittest discover tests (no Home Assistant needed)."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_path = pathlib.Path(__file__).parents[1] / "custom_components/pgnig_gas/spread.py"
_spec = importlib.util.spec_from_file_location("spread", _path)
spread = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spread)

WARSAW = ZoneInfo("Europe/Warsaw")
UTC = ZoneInfo("UTC")


def midnight(y, m, d):
    return datetime(y, m, d, tzinfo=WARSAW).astimezone(UTC)


class HourlyPointsTest(unittest.TestCase):
    def test_september_october_invoice_lands_evenly_in_both_months(self):
        # 1.09–31.10 (61 days, includes the 25 Oct DST change → 1465 hours).
        points = spread.hourly_points(midnight(2026, 9, 1), midnight(2026, 11, 1), 408.79, 13596.19)
        self.assertEqual(len(points), 61 * 24 + 1)
        self.assertEqual(points[0][0], midnight(2026, 9, 1))
        self.assertEqual(points[-1][0], midnight(2026, 11, 1) - timedelta(hours=1))
        self.assertEqual(points[-1][2], round(13596.19 + 408.79, 4))
        self.assertAlmostEqual(sum(c for _, c, _ in points), 408.79, places=6)

        by_month = {}
        by_day = {}
        for start, change, _ in points:
            local = start.astimezone(WARSAW)
            by_month[local.month] = by_month.get(local.month, 0) + change
            by_day[local.date()] = by_day.get(local.date(), 0) + change
        self.assertEqual(set(by_month), {9, 10})
        self.assertAlmostEqual(by_month[9], 408.79 * 720 / 1465, places=4)
        # Every ordinary day gets the same share, and every hour within it too.
        per_hour = points[0][1]
        self.assertTrue(all(abs(c - per_hour) < 1e-5 for _, c, _ in points))
        self.assertAlmostEqual(by_day[datetime(2026, 9, 15).date()], per_hour * 24, places=6)

    def test_sum_is_monotonic_and_continues_from_base(self):
        points = spread.hourly_points(midnight(2026, 9, 1), midnight(2026, 9, 3), 74.0, 3066.0)
        sums = [s for _, _, s in points]
        self.assertEqual(sums, sorted(sums))
        self.assertGreater(sums[0], 3066.0)
        self.assertEqual(sums[-1], 3140.0)

    def test_empty_period(self):
        self.assertEqual(spread.hourly_points(midnight(2026, 9, 1), midnight(2026, 9, 1), 10, 0), [])


if __name__ == "__main__":
    unittest.main()
