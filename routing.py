"""Plan a continuous collection tour through every requested stop.

OSRM is optional. Without it, distances are straight-line estimates and
driving times are indicative estimates at 30 km/h, never road directions.
"""

from __future__ import annotations

import json
import math
import os
from urllib.parse import urlencode
from urllib.request import urlopen


class RoutePlanningError(ValueError):
    """Invalid input, with every discovered validation error in ``errors``."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _haversine(a, b):
    lat1, lon1 = map(math.radians, (a["lat"], a["lon"]))
    lat2, lon2 = map(math.radians, (b["lat"], b["lon"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


def _request(url):
    with urlopen(url, timeout=6) as response:
        return json.load(response)


def _url(base, endpoint, points, query):
    coordinates = ";".join(f'{p["lon"]:.7f},{p["lat"]:.7f}' for p in points)
    return f'{base.rstrip("/")}/{endpoint}/v1/driving/{coordinates}?{urlencode(query)}'


def _validate(depot, stops):
    errors = []
    if not isinstance(depot, dict):
        errors.append("depot: expected an object")
        depot = {}
    if not isinstance(stops, list):
        errors.append("stops: expected a list")
        stops = []
    points = [depot] + stops
    ids = set()
    for index, point in enumerate(points):
        label = "depot" if index == 0 else f"stops[{index - 1}]"
        if not isinstance(point, dict):
            errors.append(f"{label}: expected an object")
            continue
        for key, lower, upper in (("lat", -90, 90), ("lon", -180, 180)):
            try:
                value = float(point[key])
                if not math.isfinite(value) or not lower <= value <= upper:
                    raise ValueError
                point[key] = value
            except (KeyError, TypeError, ValueError):
                errors.append(f"{label}.{key}: invalid coordinate")
        if index:
            stop_id = point.get("id")
            if stop_id is None or isinstance(stop_id, (dict, list)) or str(stop_id) == "":
                errors.append(f"{label}.id: required")
            elif str(stop_id) in ids:
                errors.append(f"{label}.id: duplicate {stop_id}")
            else:
                ids.add(str(stop_id))
            try:
                minutes = float(point.get("service_minutes", 0))
                if not math.isfinite(minutes) or minutes < 0:
                    raise ValueError
                point["service_minutes"] = minutes
            except (TypeError, ValueError):
                errors.append(f"{label}.service_minutes: must be non-negative")
    if errors:
        raise RoutePlanningError(errors)
    return points


def _air_matrices(points):
    distances = [[_haversine(a, b) for b in points] for a in points]
    durations = [[distance / 30 * 60 for distance in row] for row in distances]
    return distances, durations


def _osrm_matrices(base, points):
    result = _request(_url(base, "table", points, {"annotations": "distance,duration"}))
    if result.get("code") != "Ok":
        raise ValueError("OSRM table failed")
    distances = result["distances"]
    durations = result["durations"]
    size = len(points)
    if any(len(matrix) != size or any(len(row) != size or any(value is None for value in row) for row in matrix)
           for matrix in (distances, durations)):
        raise ValueError("OSRM table contains unreachable points")
    return [[value / 1000 for value in row] for row in distances], [[value / 60 for value in row] for row in durations]


def _tour_cost(order, durations):
    sequence = [0] + order + [0]
    return sum(durations[a][b] for a, b in zip(sequence, sequence[1:]))


def _optimize(durations, points):
    remaining = set(range(1, len(points)))
    order = []
    current = 0
    while remaining:
        nxt = min(remaining, key=lambda index: (durations[current][index], str(points[index]["id"])))
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt
    # Directed 2-opt: recompute the whole tour so one-way streets stay correct.
    improved = True
    while improved:
        improved = False
        old_cost = _tour_cost(order, durations)
        for left in range(len(order) - 1):
            for right in range(left + 1, len(order)):
                candidate = order[:left] + list(reversed(order[left:right + 1])) + order[right + 1:]
                cost = _tour_cost(candidate, durations)
                if cost < old_cost - 1e-9:
                    order, improved = candidate, True
                    break
            if improved:
                break
    return order


def _optimize_ortools(durations):
    """Find a low-travel-time closed tour using bounded guided local search."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    size = len(durations)
    manager = pywrapcp.RoutingIndexManager(size, 1, 0)
    routing = pywrapcp.RoutingModel(manager)
    callback = routing.RegisterTransitCallback(
        lambda from_index, to_index: int(round(
            durations[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)] * 60
        ))
    )
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.LOCAL_CHEAPEST_INSERTION
    parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    try:
        seconds = max(1, min(10, int(os.getenv("ROUTE_SOLVER_SECONDS", "1"))))
    except ValueError:
        seconds = 2
    parameters.time_limit.seconds = seconds
    solution = routing.SolveWithParameters(parameters)
    if solution is None:
        raise RuntimeError("OR-Tools could not find a route")
    order = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node:
            order.append(node)
        index = solution.Value(routing.NextVar(index))
    return order


def _osrm_legs(base, ordered_points):
    result = _request(_url(base, "route", ordered_points, {"overview": "false", "steps": "true", "geometries": "geojson"}))
    if result.get("code") != "Ok" or not result.get("routes"):
        raise ValueError("OSRM route failed")
    legs = result["routes"][0]["legs"]
    if len(legs) != len(ordered_points) - 1:
        raise ValueError("OSRM returned an incomplete route")
    detail = []
    for leg in legs:
        geometry = []
        for step in leg.get("steps", []):
            coordinates = step.get("geometry", {}).get("coordinates", [])
            if not coordinates:
                continue
            segment = [[lat, lon] for lon, lat in coordinates]
            geometry.extend(segment if not geometry else segment[1:])
        if not geometry:
            raise ValueError("OSRM returned a leg without geometry")
        detail.append({"distance_km": leg["distance"] / 1000, "drive_minutes": leg["duration"] / 60, "geometry": geometry})
    return detail


def plan_route(depot: dict, stops: list[dict], routing_url: str | None = None,
               preserve_order: bool = False) -> dict:
    """Return a closed tour; raises RoutePlanningError on invalid inputs.

    ``geometry`` is a list of [latitude, longitude] pairs usable by Leaflet.
    In ``air`` mode each leg is a straight line and drive time is indicative.
    ``preserve_order`` keeps the caller's stop order, including with OSRM.
    """
    # Copy inputs: validation normalizes numbers without mutating caller data.
    points = _validate(dict(depot) if isinstance(depot, dict) else depot,
                       [dict(stop) if isinstance(stop, dict) else stop for stop in stops] if isinstance(stops, list) else stops)
    mode = "air"
    algorithm = "manual-order" if preserve_order else "nearest-neighbor-2opt"
    distances, durations = _air_matrices(points)
    if routing_url:
        try:
            road_distances, road_durations = _osrm_matrices(routing_url, points)
            if preserve_order:
                road_order = list(range(1, len(points)))
                algorithm = "manual-order"
            else:
                try:
                    if len(points) >= 5:
                        road_order = _optimize_ortools(road_durations)
                        algorithm = "ortools-guided-local-search"
                    else:
                        road_order = _optimize(road_durations, points)
                        algorithm = "nearest-neighbor-2opt"
                except (ImportError, RuntimeError):
                    road_order = _optimize(road_durations, points)
                    algorithm = "nearest-neighbor-2opt"
            sequence = [0] + road_order + [0] if road_order else [0]
            road_details = _osrm_legs(routing_url, [points[index] for index in sequence]) if road_order else []
            distances, durations, order, details, mode = road_distances, road_durations, road_order, road_details, "road"
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            pass
    if mode == "air":
        if preserve_order:
            order = list(range(1, len(points)))
            algorithm = "manual-order"
        else:
            try:
                if len(points) >= 5:
                    order = _optimize_ortools(durations)
                    algorithm = "ortools-guided-local-search"
                else:
                    order = _optimize(durations, points)
                    algorithm = "nearest-neighbor-2opt"
            except (ImportError, RuntimeError):
                order = _optimize(durations, points)
                algorithm = "nearest-neighbor-2opt"
        sequence = [0] + order + [0] if order else [0]
        details = [{"distance_km": distances[a][b], "drive_minutes": durations[a][b],
                    "geometry": [[points[a]["lat"], points[a]["lon"]], [points[b]["lat"], points[b]["lon"]]]}
                   for a, b in zip(sequence, sequence[1:])]
    legs = []
    for index, (a, b) in enumerate(zip(sequence, sequence[1:])):
        leg = {"from_id": points[a].get("id"), "to_id": points[b].get("id"),
               "from_name": points[a].get("name", "Dépôt"), "to_name": points[b].get("name", "Dépôt"),
               **details[index]}
        legs.append(leg)
    service_minutes = sum(points[index]["service_minutes"] for index in order)
    distance_km = sum(leg["distance_km"] for leg in legs)
    drive_minutes = sum(leg["drive_minutes"] for leg in legs)
    return {"mode": mode, "ordered_stop_ids": [points[index]["id"] for index in order],
            "legs": legs, "distance_km": round(distance_km, 2),
            "drive_minutes": round(drive_minutes, 1), "service_minutes": round(service_minutes, 1),
            "total_minutes": round(drive_minutes + service_minutes, 1),
            "duration_is_estimate": mode == "air", "algorithm": algorithm}
