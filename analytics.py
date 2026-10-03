"""Evidence-based workload and relay-pressure summaries for the coordinator."""

from __future__ import annotations

import math
from database import DONATION_CATEGORIES
from datetime import datetime, timedelta, timezone


FULL_THRESHOLD_PCT = 80
REPEAT_SAMPLE_MIN = 4
REPEAT_SPAN_DAYS = 14
ZONE_RADIUS_KM = 1.5


def _date(value: str) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (AttributeError, TypeError, ValueError):
        return None


def _distance_km(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


def _connected_zones(points: list[dict]) -> list[list[dict]]:
    """Group nearby relays into local clusters; these are not official districts."""
    if not points:
        return []
    lat_step = ZONE_RADIUS_KM / 111.32
    max_abs_lat = max(abs(point["lat"]) for point in points)
    lon_step = ZONE_RADIUS_KM / (111.32 * max(0.05, math.cos(math.radians(max_abs_lat))))
    buckets: dict[tuple[int, int], list[dict]] = {}
    parent = {point["id"]: point["id"] for point in points}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for point in points:
        x, y = math.floor(point["lat"] / lat_step), math.floor(point["lon"] / lon_step)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                for neighbor in buckets.get((x + dx, y + dy), []):
                    if _distance_km(point, neighbor) <= ZONE_RADIUS_KM:
                        left, right = find(point["id"]), find(neighbor["id"])
                        if left != right:
                            parent[right] = left
        buckets.setdefault((x, y), []).append(point)

    grouped = {}
    for point in points:
        grouped.setdefault(find(point["id"]), []).append(point)
    return list(grouped.values())


def build_analytics(db, days: int = 90, now: datetime | None = None) -> dict:
    """Summarize observed stock, collection visits and nearby relay clusters.

    A repeat-pressure recommendation requires multiple recorded observations
    across time. Current demo stock values alone are deliberately not treated
    as historical evidence.
    """
    if days not in (30, 90, 180, 365):
        raise ValueError("days must be 30, 90, 180, or 365")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(days=days)
    start_text = start.isoformat(timespec="seconds")
    previous_start = start - timedelta(days=days)
    previous_start_text = previous_start.isoformat(timespec="seconds")

    points = [dict(row) for row in db.execute(
        "SELECT * FROM points WHERE active=1 ORDER BY id"
    )]
    by_id = {point["id"]: point for point in points}
    samples = {point_id: [] for point_id in by_id}
    for row in db.execute(
        "SELECT point_id,stock_kg,recorded_at FROM stock_history WHERE recorded_at>=? ORDER BY recorded_at",
        (start_text,),
    ):
        recorded = _date(row["recorded_at"])
        point = by_id.get(row["point_id"])
        if recorded and point:
            samples[point["id"]].append({
                "time": recorded,
                "fill": max(0.0, min(100.0, 100 * row["stock_kg"] / point["capacity_kg"])),
            })

    visits = {point_id: {"count": 0, "kg": 0.0} for point_id in by_id}
    for row in db.execute(
        """SELECT ms.point_id,ms.collected_kg,ms.visited_at
           FROM mission_stops ms JOIN missions m ON m.id=ms.mission_id
           WHERE ms.status='visited' AND ms.visited_at>=? ORDER BY ms.visited_at""",
        (start_text,),
    ):
        recorded = _date(row["visited_at"])
        point = by_id.get(row["point_id"])
        if not recorded or not point:
            continue
        visits[point["id"]]["count"] += 1
        visits[point["id"]]["kg"] += float(row["collected_kg"] or 0)

    category_totals = {category: {"current_stock_kg": 0.0, "collected_kg": 0.0, "stock_readings": 0}
                       for category in DONATION_CATEGORIES}
    for row in db.execute(
        """SELECT pds.category,pds.stock_kg FROM point_donation_stock pds
           JOIN points p ON p.id=pds.point_id WHERE p.active=1"""
    ):
        if row["category"] in category_totals:
            category_totals[row["category"]]["current_stock_kg"] += row["stock_kg"]
    for row in db.execute(
        """SELECT category,COUNT(*) AS readings FROM donation_stock_history
           WHERE recorded_at>=? GROUP BY category""", (start_text,)
    ):
        if row["category"] in category_totals:
            category_totals[row["category"]]["stock_readings"] = row["readings"]
    for row in db.execute(
        """SELECT d.category,SUM(d.collected_kg) AS kg FROM mission_stop_donations d
           JOIN mission_stops ms ON ms.id=d.mission_stop_id
           WHERE ms.status='visited' AND ms.visited_at>=? GROUP BY d.category""", (start_text,)
    ):
        if row["category"] in category_totals:
            category_totals[row["category"]]["collected_kg"] = row["kg"] or 0

    point_results = []
    weekly = {}
    weekdays = {day: {"count": 0, "full": 0, "fill_total": 0.0} for day in range(7)}
    for point in points:
        readings = sorted(samples[point["id"]], key=lambda sample: sample["time"])
        fills = [reading["fill"] for reading in readings]
        sample_count = len(readings)
        span_days = ((readings[-1]["time"] - readings[0]["time"]).total_seconds() / 86400) if sample_count > 1 else 0.0
        average = sum(fills) / sample_count if sample_count else None
        full_count = sum(fill >= FULL_THRESHOLD_PCT for fill in fills)
        full_rate = full_count / sample_count if sample_count else None
        mature = sample_count >= REPEAT_SAMPLE_MIN and span_days >= REPEAT_SPAN_DAYS
        repeated_pressure = bool(mature and average is not None and average >= 70 and full_rate >= 0.5)
        point_results.append({
            "id": point["id"], "name": point["name"], "address": point["address"],
            "lat": point["lat"], "lon": point["lon"],
            "current_fill_pct": round(100 * point["stock_kg"] / point["capacity_kg"], 1),
            "average_fill_pct": round(average, 1) if average is not None else None,
            "peak_fill_pct": round(max(fills), 1) if fills else None,
            "full_observations": full_count,
            "observations": sample_count,
            "full_rate_pct": round(100 * full_rate, 1) if full_rate is not None else None,
            "span_days": round(span_days, 1),
            "repeat_pressure": repeated_pressure,
            "history_sufficient": mature,
            "visit_count": visits[point["id"]]["count"],
            "collected_kg": round(visits[point["id"]]["kg"], 2),
        })
        for reading in readings:
            monday = reading["time"].date() - timedelta(days=reading["time"].weekday())
            bucket = weekly.setdefault(monday.isoformat(), {"count": 0, "fill_total": 0.0, "full": 0})
            bucket["count"] += 1
            bucket["fill_total"] += reading["fill"]
            bucket["full"] += reading["fill"] >= FULL_THRESHOLD_PCT
            day = weekdays[reading["time"].weekday()]
            day["count"] += 1
            day["fill_total"] += reading["fill"]
            day["full"] += reading["fill"] >= FULL_THRESHOLD_PCT

    zones = []
    point_result_by_id = {point["id"]: point for point in point_results}
    for index, members in enumerate(_connected_zones(points), start=1):
        zone_points = [point_result_by_id[point["id"]] for point in members]
        readings = sum(point["observations"] for point in zone_points)
        full = sum(point["full_observations"] for point in zone_points)
        weighted_fill = sum(
            (point["average_fill_pct"] or 0) * point["observations"] for point in zone_points
        ) / readings if readings else None
        times = [sample["time"] for point in members for sample in samples[point["id"]]]
        span_days = (max(times) - min(times)).total_seconds() / 86400 if len(times) > 1 else 0.0
        pressured_points = sum(point["repeat_pressure"] for point in zone_points)
        full_rate = full / readings if readings else None
        candidate = bool(
            readings >= 6 and span_days >= REPEAT_SPAN_DAYS and weighted_fill is not None
            and weighted_fill >= 70 and full_rate >= 0.5
        )
        zones.append({
            "id": index,
            "name": f"Secteur {index}",
            "lat": round(sum(point["lat"] for point in members) / len(members), 6),
            "lon": round(sum(point["lon"] for point in members) / len(members), 6),
            "point_count": len(members),
            "observations": readings,
            "span_days": round(span_days, 1),
            "average_fill_pct": round(weighted_fill, 1) if weighted_fill is not None else None,
            "full_observations": full,
            "full_rate_pct": round(100 * full_rate, 1) if full_rate is not None else None,
            "pressured_points": pressured_points,
            "visit_count": sum(point["visit_count"] for point in zone_points),
            "collected_kg": round(sum(point["collected_kg"] for point in zone_points), 2),
            "consider_new_relay": candidate,
            "point_ids": [point["id"] for point in members],
        })
    zones.sort(key=lambda zone: (not zone["consider_new_relay"], -(zone["full_rate_pct"] or 0), zone["id"]))

    samples_total = sum(point["observations"] for point in point_results)
    full_total = sum(point["full_observations"] for point in point_results)
    mature_count = sum(point["history_sufficient"] for point in point_results)
    visits_total = sum(point["visit_count"] for point in point_results)
    kg_total = round(sum(point["collected_kg"] for point in point_results), 2)
    previous_stops = db.execute(
        """SELECT COUNT(*),COALESCE(SUM(collected_kg),0) FROM mission_stops
           WHERE status='visited' AND visited_at>=? AND visited_at<?""",
        (previous_start_text, start_text),
    ).fetchone()
    previous_readings = db.execute(
        """SELECT COUNT(*),COALESCE(SUM(CASE WHEN sh.stock_kg/p.capacity_kg>=0.8 THEN 1 ELSE 0 END),0)
           FROM stock_history sh JOIN points p ON p.id=sh.point_id
           WHERE sh.recorded_at>=? AND sh.recorded_at<? AND p.active=1""",
        (previous_start_text, start_text),
    ).fetchone()
    previous_visits = int(previous_stops[0])
    previous_kg = round(float(previous_stops[1]), 2)
    previous_obs = int(previous_readings[0])
    previous_full_rate = round(100 * int(previous_readings[1]) / previous_obs, 1) if previous_obs else None
    trend = [
        {"week": week, "observations": value["count"],
         "average_fill_pct": round(value["fill_total"] / value["count"], 1),
         "full_rate_pct": round(100 * value["full"] / value["count"], 1)}
        for week, value in sorted(weekly.items())
    ]
    weekday_trend = [
        {"weekday": index, "observations": value["count"],
         "average_fill_pct": round(value["fill_total"] / value["count"], 1) if value["count"] else None,
         "full_rate_pct": round(100 * value["full"] / value["count"], 1) if value["count"] else None}
        for index, value in weekdays.items()
    ]
    point_results.sort(key=lambda point: (
        -point["collected_kg"], -point["visit_count"],
        -(point["average_fill_pct"] or 0), point["name"].casefold(),
    ))
    return {
        "period_days": days,
        "period_start": start_text,
        "period_end": now.isoformat(timespec="seconds"),
        "comparison": {
            "previous_start": previous_start_text,
            "previous_end": start_text,
            "current_visits": visits_total,
            "previous_visits": previous_visits,
            "current_collected_kg": kg_total,
            "previous_collected_kg": previous_kg,
            "current_full_rate_pct": round(100 * full_total / samples_total, 1) if samples_total else None,
            "previous_full_rate_pct": previous_full_rate,
            "previous_observations": previous_obs,
        },
        "threshold_pct": FULL_THRESHOLD_PCT,
        "repeat_sample_min": REPEAT_SAMPLE_MIN,
        "repeat_span_days": REPEAT_SPAN_DAYS,
        "zone_radius_km": ZONE_RADIUS_KM,
        "metrics": {
            "active_points": len(points), "observations": samples_total,
            "history_ready_points": mature_count,
            "history_coverage_pct": round(100 * mature_count / len(points), 1) if points else 0,
            "full_observations": full_total,
            "full_rate_pct": round(100 * full_total / samples_total, 1) if samples_total else None,
            "repeat_pressure_points": sum(point["repeat_pressure"] for point in point_results),
            "visited_stops": visits_total, "collected_kg": kg_total,
            "average_kg_per_visit": round(kg_total / visits_total, 2) if visits_total else None,
        },
        "trend": trend,
        "weekday_trend": weekday_trend,
        "donation_categories": [
            {"category": category, "current_stock_kg": round(values["current_stock_kg"], 2),
             "collected_kg": round(values["collected_kg"], 2), "stock_readings": values["stock_readings"]}
            for category, values in category_totals.items()
        ],
        "points": point_results,
        "zones": zones,
    }
