import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database
from analytics import build_analytics


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "analytics.sqlite3"
        database.initialize(path=self.db_path, admin_username="admin", admin_password="long-password-123")
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        self.db = database.connect(self.db_path)
        self.db.execute("UPDATE points SET lat=50.95,lon=1.85,capacity_kg=100 WHERE id=1")
        self.db.execute("UPDATE points SET lat=50.955,lon=1.855,capacity_kg=100 WHERE id=2")
        for point_id in (1, 2):
            for days_ago, stock in ((80, 97), (28, 90), (21, 95), (14, 68), (1, 100)):
                timestamp = (self.now - timedelta(days=days_ago)).isoformat(timespec="seconds")
                self.db.execute(
                    "INSERT INTO stock_history(point_id,stock_kg,recorded_at,user_id) VALUES (?,?,?,1)",
                    (point_id, stock, timestamp),
                )
        self.db.execute(
            """INSERT INTO missions(title,created_at,created_by,status,routing_mode,distance_km,
               geometry_json,assigned_to) VALUES (?,?,?,?,?,?,?,?)""",
            ("Test mission", self.now.isoformat(), 1, "in_progress", "air", 2.0, "[]", None),
        )
        self.db.execute(
            """INSERT INTO mission_stops(mission_id,point_id,position,status,planned_stock_kg,
               collected_kg,visited_at) VALUES (1,1,1,'visited',90,7,?)""",
            ((self.now - timedelta(days=1)).isoformat(timespec="seconds"),),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_repeated_pressure_and_collections_create_evidence_based_zone(self):
        result = build_analytics(self.db, 90, now=self.now)
        self.assertEqual(result["metrics"]["observations"], 10)
        self.assertEqual(result["metrics"]["visited_stops"], 1)
        self.assertEqual(result["metrics"]["collected_kg"], 7)
        self.assertEqual(len(result["weekday_trend"]), 7)
        self.assertEqual(sum(day["observations"] for day in result["weekday_trend"]), 10)
        point = next(item for item in result["points"] if item["id"] == 1)
        self.assertTrue(point["history_sufficient"])
        self.assertTrue(point["repeat_pressure"])
        zone = next(item for item in result["zones"] if 1 in item["point_ids"])
        self.assertTrue(zone["consider_new_relay"])
        self.assertIn(2, zone["point_ids"])

    def test_single_recent_reading_never_recommends_a_new_relay(self):
        self.db.execute("DELETE FROM stock_history")
        self.db.execute("DELETE FROM mission_stops")
        self.db.commit()
        result = build_analytics(self.db, 30, now=self.now)
        self.assertEqual(result["metrics"]["observations"], 0)
        self.assertEqual(result["metrics"]["repeat_pressure_points"], 0)
        self.assertFalse(any(zone["consider_new_relay"] for zone in result["zones"]))

    def test_period_excludes_old_observations_and_rejects_unknown_periods(self):
        result = build_analytics(self.db, 30, now=self.now)
        self.assertEqual(result["metrics"]["observations"], 8)
        self.assertEqual(result["comparison"]["previous_collected_kg"], 0)
        self.assertEqual(result["comparison"]["current_collected_kg"], 7)
        self.assertIsNone(result["comparison"]["previous_full_rate_pct"])
        with self.assertRaises(ValueError):
            build_analytics(self.db, 60, now=self.now)


if __name__ == "__main__":
    unittest.main()
