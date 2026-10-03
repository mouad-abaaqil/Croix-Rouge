"""Red Collect: a small self-hosted collection planning application."""

import csv
import io
import json
import os
import re
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import database as data
from analytics import build_analytics
from routing import RoutePlanningError, plan_route


load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("APP_HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=1024 * 1024,
)
data.migrate_existing()


@app.before_request
def before_request():
    g.db = data.connect()
    g.user = None
    if session.get("user_id"):
        row = g.db.execute("SELECT id,username,name,role,session_version FROM users WHERE id=? AND active=1", (session["user_id"],)).fetchone()
        if row and session.get("session_version", 0) == row["session_version"]:
            g.user = dict(row)
        else:
            session.clear()
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.endpoint != "login":
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not supplied or not secrets.compare_digest(supplied, session.get("csrf_token", "")):
            abort(403, "Invalid CSRF token")


@app.teardown_request
def teardown_request(_error):
    db = getattr(g, "db", None)
    if db is not None:
        db.close()


@app.context_processor
def template_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"current_user": g.user, "csrf_token": session["csrf_token"]}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            if request.path.startswith("/api/"):
                return jsonify(error="login_required"), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def coordinator_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "coordinator":
            if request.path.startswith("/api/"):
                return jsonify(error="forbidden"), 403
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, "Expected JSON object")
    return value


def number(value, minimum=None, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        abort(400, "Invalid number")
    if not (result == result and abs(result) != float("inf")):
        abort(400, "Invalid number")
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        abort(400, "Number out of range")
    return result


def clean_text(value, limit):
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()[:limit]


def mission_dict(row, include_stops=False):
    mission = dict(row)
    mission["geometry"] = json.loads(mission.pop("geometry_json"))
    if include_stops:
        rows = g.db.execute(
            """SELECT ms.point_id,ms.position,ms.status,ms.collected_kg,ms.planned_stock_kg,
                  ms.visited_at,p.name,p.address,p.lat,p.lon,p.stock_kg,p.capacity_kg
               FROM mission_stops ms JOIN points p ON p.id=ms.point_id
               WHERE ms.mission_id=? ORDER BY ms.position""", (mission["id"],)
        )
        mission["stops"] = [dict(stop) for stop in rows]
    return mission


def get_mission(mission_id):
    row = g.db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if row is None:
        abort(404)
    return mission_dict(row, include_stops=True)


@app.get("/login")
def login():
    return render_template("login.html", error=None)


@app.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    row = g.db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return render_template("login.html", error="invalid"), 401
    session.clear()
    session["user_id"] = row["id"]
    session["session_version"] = row["session_version"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("dashboard"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", page="dashboard")


@app.get("/analytics")
@coordinator_required
def analytics_page():
    return render_template("analytics.html", page="analytics")


@app.get("/api/analytics")
@coordinator_required
def analytics_api():
    try:
        days = int(request.args.get("days", "90"))
    except ValueError:
        abort(400, "Invalid analysis period")
    if days not in (30, 90, 180, 365):
        abort(400, "Invalid analysis period")
    return jsonify(build_analytics(g.db, days=days))


@app.get("/assets/croix_rouge_logo.png")
def logo():
    return send_from_directory(data.ROOT / "assets", "croix_rouge_logo.png")


@app.get("/points")
@login_required
def points_page():
    return render_template("points.html", page="points")


@app.get("/planner")
@login_required
def planner_page():
    return render_template("planner.html", page="planner")


@app.get("/settings")
@coordinator_required
def settings_page():
    return render_template("settings.html", page="settings")


@app.get("/missions")
@login_required
def missions_page():
    return render_template("missions.html", page="missions")


@app.get("/missions/<int:mission_id>")
@login_required
def mission_page(mission_id):
    get_mission(mission_id)
    return render_template("mission_detail.html", page="missions", mission_id=mission_id)


@app.get("/api/bootstrap")
@login_required
def bootstrap():
    missions = [mission_dict(row, include_stops=True) for row in g.db.execute("SELECT * FROM missions ORDER BY id DESC LIMIT 100")]
    config = dict(g.db.execute("SELECT key,value FROM settings").fetchall())
    users = [dict(row) for row in g.db.execute("SELECT id,username,name,role,active FROM users ORDER BY active DESC,name")] if g.user["role"] == "coordinator" else []
    return jsonify(user=g.user, users=users, points=data.points(g.db), depot=data.depot(g.db), missions=missions, config=config)


@app.post("/api/users")
@coordinator_required
def add_user():
    body = payload()
    username = clean_text(body.get("username", ""), 80)
    name = clean_text(body.get("name", ""), 120)
    password = body.get("password", "")
    role = body.get("role", "volunteer")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,80}", username) or not name or not isinstance(password, str) or len(password) < 12 or role not in ("volunteer", "coordinator"):
        abort(400, "Invalid user details")
    try:
        with g.db:
            cursor = g.db.execute("INSERT INTO users(username,name,password_hash,role) VALUES (?,?,?,?)",
                                  (username,name,generate_password_hash(password),role))
    except sqlite3.IntegrityError:
        return jsonify(error="username_taken"), 409
    return jsonify(user={"id":cursor.lastrowid,"username":username,"name":name,"role":role,"active":1}), 201


@app.patch("/api/users/<int:user_id>")
@coordinator_required
def edit_user(user_id):
    row = g.db.execute("SELECT id,username,name,role,active,session_version FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        abort(404)
    body = payload()
    name = clean_text(body.get("name", row["name"]), 120)
    if not name:
        abort(400, "Name required")
    active = row["active"]
    if "active" in body:
        if not isinstance(body["active"], bool):
            abort(400, "Invalid active value")
        active = int(body["active"])
    password = body.get("password")
    if password is not None and (not isinstance(password, str) or len(password) < 12):
        abort(400, "Password must contain at least 12 characters")
    if row["role"] == "coordinator" and (not active or name != row["name"]):
        # Keep at least one active coordinator to administer the unit.
        if not active:
            active_admins = g.db.execute("SELECT COUNT(*) FROM users WHERE role='coordinator' AND active=1").fetchone()[0]
            if active_admins <= 1:
                abort(400, "The last coordinator cannot be deactivated")
    if user_id == g.user["id"] and not active:
        abort(400, "You cannot deactivate your own account")
    with g.db:
        if password is not None:
            g.db.execute("UPDATE users SET name=?,active=?,password_hash=?,session_version=session_version+1 WHERE id=?",
                         (name,active,generate_password_hash(password),user_id))
        else:
            g.db.execute("UPDATE users SET name=?,active=? WHERE id=?", (name,active,user_id))
    return jsonify(user={"id":user_id,"username":row["username"],"name":name,"role":row["role"],"active":active})


@app.get("/api/geocode")
@coordinator_required
def geocode_address():
    """User-triggered single address search; cached and globally rate limited."""
    query = clean_text(request.args.get("q", ""), 200)
    if len(query) < 4:
        abort(400, "Enter at least four characters")
    language = "en" if request.args.get("lang") == "en" else "fr"
    cache_key = f"{language}:{query.casefold()}"
    cached = g.db.execute("SELECT result_json FROM geocode_cache WHERE query=?", (cache_key,)).fetchone()
    if cached:
        return jsonify(results=json.loads(cached[0]), attribution="© OpenStreetMap contributors")
    last = g.db.execute("SELECT value FROM settings WHERE key='geocode_last_request'").fetchone()
    if last and time.time() - float(last[0]) < 1.0:
        return jsonify(error="geocode_wait"), 429
    base_url = os.getenv("GEOCODER_URL", "https://nominatim.openstreetmap.org/search")
    params = urlencode({"format":"jsonv2", "limit":5, "countrycodes":"fr", "q":query, "accept-language":language})
    req = Request(f"{base_url}?{params}", headers={"User-Agent":"RedCollect/1.0 (+https://github.com/mouad-abaaqil/Croix-Rouge)"})
    with g.db:
        g.db.execute("INSERT INTO settings(key,value) VALUES('geocode_last_request',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(time.time()),))
    try:
        with urlopen(req, timeout=8) as response:
            raw_results = json.load(response)
    except Exception:
        app.logger.exception("Address search failed")
        return jsonify(error="geocode_failed"), 502
    results = [{"lat":float(item["lat"]), "lon":float(item["lon"]),
                "address":item.get("display_name", query)} for item in raw_results if "lat" in item and "lon" in item]
    with g.db:
        g.db.execute("INSERT OR REPLACE INTO geocode_cache(query,result_json,cached_at) VALUES (?,?,?)",
                     (cache_key,json.dumps(results,ensure_ascii=False),data.now()))
    return jsonify(results=results, attribution="© OpenStreetMap contributors")


@app.patch("/api/settings")
@coordinator_required
def edit_settings():
    body = payload()
    allowed = {"unit_name", "depot_address", "depot_lat", "depot_lon", "demo_data"}
    if not body or any(key not in allowed for key in body):
        abort(400, "Unknown setting")
    values = {}
    for key, value in body.items():
        if key in {"depot_lat", "depot_lon"}:
            values[key] = str(number(value, -90 if key == "depot_lat" else -180, 90 if key == "depot_lat" else 180))
        elif key == "demo_data":
            if value not in ("0", "1"):
                abort(400, "Invalid demo setting")
            values[key] = value
        else:
            value = clean_text(value, 300)
            if not value:
                abort(400, "Empty setting")
            values[key] = value
    with g.db:
        for key, value in values.items():
            g.db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    return jsonify(depot=data.depot(g.db))


@app.post("/api/points")
@coordinator_required
def add_point():
    body = payload()
    name = clean_text(body.get("name", ""), 160)
    address = clean_text(body.get("address", ""), 300)
    if not name or not address:
        abort(400, "Name and address required")
    lat = number(body.get("lat"), -90, 90)
    lon = number(body.get("lon"), -180, 180)
    capacity = number(body.get("capacity_kg"), 0.001, 100000)
    stock = number(body.get("stock_kg", 0), 0, capacity)
    pickup = int(number(body.get("estimated_pickup_min", 10), 0, 1440))
    with g.db:
        cursor = g.db.execute("""INSERT INTO points(name,address,lat,lon,capacity_kg,stock_kg,
             estimated_pickup_min,updated_at) VALUES (?,?,?,?,?,?,?,?)""",
             (name, address, lat, lon, capacity, stock, pickup, data.now()))
        g.db.execute("INSERT INTO stock_history(point_id,stock_kg,recorded_at,user_id) VALUES (?,?,?,?)",
                     (cursor.lastrowid, stock, data.now(), g.user["id"]))
    return jsonify(point=data.point_dict(g.db.execute("SELECT * FROM points WHERE id=?", (cursor.lastrowid,)).fetchone())), 201


@app.patch("/api/points/<int:point_id>")
@coordinator_required
def edit_point(point_id):
    body = payload()
    row = g.db.execute("SELECT * FROM points WHERE id=?", (point_id,)).fetchone()
    if row is None:
        abort(404)
    values = dict(row)
    for field in ("name", "address"):
        if field in body:
            values[field] = clean_text(body[field], 160 if field == "name" else 300)
            if not values[field]:
                abort(400, "Empty text")
    for field, bounds in (("lat",(-90,90)),("lon",(-180,180)),("capacity_kg",(0.001,100000)),("estimated_pickup_min",(0,1440))):
        if field in body:
            values[field] = number(body[field], *bounds)
    if values["capacity_kg"] < values["stock_kg"]:
        abort(400, "Capacity below stock")
    if "active" in body:
        if not isinstance(body["active"], bool):
            abort(400, "Invalid active value")
        values["active"] = int(body["active"])
    with g.db:
        g.db.execute("""UPDATE points SET name=?,address=?,lat=?,lon=?,capacity_kg=?,
             estimated_pickup_min=?,active=? WHERE id=?""",
             (values["name"],values["address"],values["lat"],values["lon"],values["capacity_kg"],
              values["estimated_pickup_min"],values["active"],point_id))
    return jsonify(point=data.point_dict(g.db.execute("SELECT * FROM points WHERE id=?", (point_id,)).fetchone()))


@app.post("/api/points/<int:point_id>/stock")
@login_required
def update_stock(point_id):
    row = g.db.execute("SELECT * FROM points WHERE id=? AND active=1", (point_id,)).fetchone()
    if row is None:
        abort(404)
    stock = number(payload().get("stock_kg"), 0, row["capacity_kg"])
    with g.db:
        g.db.execute("UPDATE points SET stock_kg=?,updated_at=? WHERE id=?", (stock, data.now(), point_id))
        g.db.execute("INSERT INTO stock_history(point_id,stock_kg,recorded_at,user_id) VALUES (?,?,?,?)",
                     (point_id, stock, data.now(), g.user["id"]))
    return jsonify(point=data.point_dict(g.db.execute("SELECT * FROM points WHERE id=?", (point_id,)).fetchone()))


def planned(body):
    ids = body.get("stop_ids", [])
    if not isinstance(ids, list) or not ids or len(ids) > 50 or any(type(item) is not int for item in ids) or len(ids) != len(set(ids)):
        abort(400, "Select 1 to 50 distinct points")
    lookup = {point["id"]: point for point in data.points(g.db)}
    if any(item not in lookup for item in ids):
        abort(400, "Unknown or inactive point")
    stops = [lookup[item] for item in ids]
    routing_stops = [{"id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                      "service_minutes": p["estimated_pickup_min"]} for p in stops]
    try:
        route = plan_route(data.depot(g.db), routing_stops, os.getenv("ROUTING_URL"), preserve_order=body.get("preserve_order") is True)
    except RoutePlanningError as error:
        return None, jsonify(error="routing_error", details=error.errors), 400
    ordered = [lookup[item] for item in route["ordered_stop_ids"]]
    geometry = []
    for leg in route["legs"]:
        segment = leg["geometry"]
        geometry.extend(segment[1:] if geometry else segment)
    result = {
        "stops": [{**p, "point_id": p["id"]} for p in ordered],
        "geometry": geometry,
        "distance_km": route["distance_km"],
        "drive_minutes": route["drive_minutes"],
        "service_minutes": route["service_minutes"],
        "total_minutes": route["total_minutes"],
        "routing_mode": route["mode"],
        "algorithm": route["algorithm"],
        "warnings": (["air_warning"] if route["mode"] == "air" else ["no_live_traffic"]),
    }
    return result, None, None


@app.post("/api/missions/plan")
@coordinator_required
def preview_plan():
    result, error, status = planned(payload())
    return (error, status) if error is not None else jsonify(result)


@app.post("/api/missions")
@coordinator_required
def create_mission():
    body = payload()
    result, error, status = planned(body)
    if error is not None:
        return error, status
    title = clean_text(body.get("title", ""), 160) or f"Collecte {data.now()[:10]}"
    assigned_to = body.get("assigned_to")
    if assigned_to is not None:
        if type(assigned_to) is not int or not g.db.execute("SELECT 1 FROM users WHERE id=? AND active=1", (assigned_to,)).fetchone():
            abort(400, "Unknown volunteer")
    with g.db:
        cursor = g.db.execute("""INSERT INTO missions(title,created_at,created_by,routing_mode,
             distance_km,drive_minutes,total_minutes,geometry_json,algorithm,assigned_to)
             VALUES (?,?,?,?,?,?,?,?,?,?)""",
             (title,data.now(),g.user["id"],result["routing_mode"],result["distance_km"],
              result["drive_minutes"],result["total_minutes"],json.dumps(result["geometry"]),result["algorithm"],assigned_to))
        for position, point in enumerate(result["stops"], 1):
            g.db.execute("""INSERT INTO mission_stops(mission_id,point_id,position,planned_stock_kg)
                 VALUES (?,?,?,?)""", (cursor.lastrowid,point["id"],position,point["stock_kg"]))
    return jsonify(mission=get_mission(cursor.lastrowid)), 201


@app.get("/api/missions/<int:mission_id>")
@login_required
def mission_api(mission_id):
    return jsonify(mission=get_mission(mission_id), depot=data.depot(g.db))


@app.patch("/api/missions/<int:mission_id>/stops/<int:point_id>")
@login_required
def update_stop(mission_id, point_id):
    mission = get_mission(mission_id)
    if g.user["role"] != "coordinator" and mission["assigned_to"] not in (None, g.user["id"]):
        return jsonify(error="forbidden"), 403
    body = payload()
    status = body.get("status")
    if status not in ("pending", "visited", "skipped"):
        abort(400, "Invalid status")
    selected = next((stop for stop in mission["stops"] if stop["point_id"] == point_id), None)
    if selected is None:
        abort(404)
    if selected["status"] == "visited" and status != "visited":
        abort(400, "A visited stop cannot be reset")
    collected = None
    if status == "visited":
        collected = number(body.get("collected_kg", 0), 0, max(selected["planned_stock_kg"], selected["collected_kg"] or 0))
        previous = selected["collected_kg"] or 0
    with g.db:
        changed = g.db.execute("""UPDATE mission_stops SET status=?,collected_kg=?,visited_at=?
             WHERE mission_id=? AND point_id=? AND status=? AND collected_kg IS ?""",
             (status,collected,data.now() if status != "pending" else None,mission_id,point_id,
              selected["status"],selected["collected_kg"]))
        if changed.rowcount != 1:
            abort(409, "Stop changed; reload the mission")
        if status == "visited" and collected != previous:
            delta = previous - collected
            updated = g.db.execute("""UPDATE points SET stock_kg=stock_kg+?,updated_at=?
                 WHERE id=? AND stock_kg+? BETWEEN 0 AND capacity_kg""",
                 (delta,data.now(),point_id,delta))
            if updated.rowcount != 1:
                abort(409, "Stock changed; reload the mission")
            new_stock = g.db.execute("SELECT stock_kg FROM points WHERE id=?", (point_id,)).fetchone()[0]
            g.db.execute("INSERT INTO stock_history(point_id,stock_kg,recorded_at,user_id) VALUES (?,?,?,?)",
                         (point_id,new_stock,data.now(),g.user["id"]))
        statuses = [row[0] for row in g.db.execute("SELECT status FROM mission_stops WHERE mission_id=?", (mission_id,))]
        mission_status = "completed" if all(item != "pending" for item in statuses) else "in_progress" if any(item != "pending" for item in statuses) else "planned"
        g.db.execute("UPDATE missions SET status=? WHERE id=?", (mission_status,mission_id))
    return jsonify(mission=get_mission(mission_id))


@app.get("/api/missions/<int:mission_id>/export.csv")
@login_required
def export_mission(mission_id):
    mission = get_mission(mission_id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    lang = "en" if request.args.get("lang") == "en" else "fr"
    writer.writerow(["Position", "Point", "Address", "Latitude", "Longitude", "Status", "Planned stock (kg)", "Collected (kg)"]
                    if lang == "en" else
                    ["Position", "Point", "Adresse", "Latitude", "Longitude", "Statut", "Stock prévu (kg)", "Collecté (kg)"])
    for stop in mission["stops"]:
        writer.writerow([stop["position"],stop["name"],stop["address"],stop["lat"],stop["lon"],stop["status"],stop["planned_stock_kg"],stop["collected_kg"] or ""])
    return Response("\ufeff" + stream.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=mission-{mission_id}.csv"})


def email_content(mission, lang):
    french = lang != "en"
    title = "Mission de collecte" if french else "Collection mission"
    lines = [f"{title}: {mission['title']}", "", f"{len(mission['stops'])} " + ("arrêts" if french else "stops")]
    for stop in mission["stops"]:
        lines.append(f"{stop['position']}. {stop['name']} — {stop['address']}")
    lines.extend(["", ("Distance estimée" if french else "Estimated distance") + f": {mission['distance_km']:.1f} km",
                  ("Ouvrir la mission" if french else "Open mission") + f": {request.host_url.rstrip('/')}/missions/{mission['id']}"])
    if mission["routing_mode"] == "air":
        lines.append("Distance à vol d'oiseau, trajet routier non disponible." if french else "Straight-line distance; road route unavailable.")
    return title + " — " + mission["title"], "\n".join(lines)


@app.get("/api/missions/<int:mission_id>/email-preview")
@coordinator_required
def email_preview(mission_id):
    mission = get_mission(mission_id)
    lang = "en" if request.args.get("lang") == "en" else "fr"
    subject, body = email_content(mission, lang)
    return jsonify(subject=subject, body=body)


@app.post("/api/missions/<int:mission_id>/email")
@coordinator_required
def send_mission_email(mission_id):
    mission = get_mission(mission_id)
    body = payload()
    recipients = body.get("recipients")
    if not isinstance(recipients, list) or not recipients or len(recipients) > 20 or any(not isinstance(item,str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",item) for item in recipients):
        abort(400, "Invalid recipients")
    required = ["SMTP_SERVER", "SMTP_USERNAME", "SMTP_PASSWORD", "SENDER_EMAIL"]
    if any(not os.getenv(key) for key in required):
        return jsonify(error="smtp_not_configured"), 503
    subject, content = email_content(mission, "en" if body.get("lang") == "en" else "fr")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["SENDER_EMAIL"]
    msg["To"] = ", ".join(recipients)
    msg.set_content(content)
    try:
        with smtplib.SMTP(os.environ["SMTP_SERVER"], int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            server.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
    except (OSError, smtplib.SMTPException):
        app.logger.exception("Mission email failed")
        return jsonify(error="smtp_failed"), 502
    return jsonify(sent=True)


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
def json_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error=error.description), error.code
    return error


if __name__ == "__main__":
    import getpass
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        username = os.getenv("APP_ADMIN_USER") or input("Admin username: ").strip()
        password = os.getenv("APP_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
        if not username or len(password) < 12:
            raise SystemExit("Username required; password must contain at least 12 characters")
        data.initialize(admin_username=username, admin_password=password)
        print("Database initialized with Calais demo data.")
    elif len(sys.argv) > 1 and sys.argv[1] == "add-user":
        role = sys.argv[2] if len(sys.argv) > 2 else "volunteer"
        if role not in ("volunteer", "coordinator"):
            raise SystemExit("Role must be volunteer or coordinator")
        username = input("Username: ").strip()
        name = input("Display name: ").strip() or username
        password = getpass.getpass("Password: ")
        if not username or len(password) < 12:
            raise SystemExit("Username required; password must contain at least 12 characters")
        with data.connect() as db:
            db.execute("INSERT INTO users(username,name,password_hash,role) VALUES (?,?,?,?)",
                       (username,name,generate_password_hash(password),role))
        print(f"User {username} added as {role}.")
    else:
        if not Path(os.getenv("DATABASE_PATH", data.DEFAULT_DB)).exists():
            raise SystemExit("Initialize the database first: python webapp.py init")
        app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
