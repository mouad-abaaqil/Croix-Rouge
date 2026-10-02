import unittest
from unittest.mock import patch

from routing import RoutePlanningError, plan_route


DEPOT = {"lat": 50.95, "lon": 1.86, "name": "Depot"}
STOPS = [
    {"id": "A", "name": "A", "lat": 50.96, "lon": 1.87, "service_minutes": 10},
    {"id": "B", "name": "B", "lat": 50.94, "lon": 1.85, "service_minutes": 20},
]


class RoutingTests(unittest.TestCase):
    def test_air_tour_visits_every_stop_and_returns_to_depot(self):
        result = plan_route(DEPOT, STOPS)
        self.assertEqual(result["mode"], "air")
        self.assertEqual(set(result["ordered_stop_ids"]), {"A", "B"})
        self.assertEqual(len(result["legs"]), 3)
        self.assertEqual(result["legs"][0]["from_id"], None)
        self.assertEqual(result["legs"][-1]["to_id"], None)
        self.assertEqual(result["service_minutes"], 30)
        self.assertTrue(result["duration_is_estimate"])

    def test_invalid_coordinates_report_all_errors(self):
        with self.assertRaises(RoutePlanningError) as context:
            plan_route({"lat": 100, "lon": "bad"}, [{"id": "A", "lat": None, "lon": 1}])
        self.assertEqual(len(context.exception.errors), 3)

    def test_osrm_failure_falls_back_without_dropping_stops(self):
        with patch("routing._request", side_effect=OSError("offline")):
            result = plan_route(DEPOT, STOPS, "https://osrm.example")
        self.assertEqual(result["mode"], "air")
        self.assertEqual(set(result["ordered_stop_ids"]), {"A", "B"})

    def test_preserve_order_keeps_manual_stop_sequence_and_closes_tour(self):
        result = plan_route(DEPOT, [STOPS[1], STOPS[0]], preserve_order=True)
        self.assertEqual(result["ordered_stop_ids"], ["B", "A"])
        self.assertEqual([(leg["from_id"], leg["to_id"]) for leg in result["legs"]],
                         [(None, "B"), ("B", "A"), ("A", None)])

    def test_road_route_uses_detailed_leg_geometry(self):
        table = {"code": "Ok", "distances": [[0, 1000], [1000, 0]],
                 "durations": [[0, 120], [120, 0]]}
        route = {"code": "Ok", "routes": [{"legs": [
            {"distance": 1000, "duration": 120, "steps": [{"geometry": {"coordinates": [[1.86, 50.95], [1.87, 50.96]]}}]},
            {"distance": 1000, "duration": 120, "steps": [{"geometry": {"coordinates": [[1.87, 50.96], [1.86, 50.95]]}}]},
        ]}]}
        with patch("routing._request", side_effect=[table, route]):
            result = plan_route(DEPOT, STOPS[:1], "https://osrm.example")
        self.assertEqual(result["mode"], "road")
        self.assertEqual(result["distance_km"], 2)
        self.assertEqual(result["legs"][0]["geometry"][0], [50.95, 1.86])


if __name__ == "__main__":
    unittest.main()
