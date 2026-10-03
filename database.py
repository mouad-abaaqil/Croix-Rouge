"""SQLite persistence for the Calais pilot application."""

import csv
import os
import sqlite3
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "instance" / "redcollect.sqlite3"

DONATION_CATEGORIES = (
    "clothing", "shoes", "hygiene", "baby", "bedding", "food", "other", "unclassified",
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    db_path = Path(path or os.getenv("DATABASE_PATH", DEFAULT_DB))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


SCHEMA = """
CREATE TABLE IF NOT EXISTS local_units (
 id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 source_url TEXT NOT NULL, postal_code TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS unit_settings (
 unit_id INTEGER NOT NULL REFERENCES local_units(id), key TEXT NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(unit_id,key)
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('coordinator','volunteer')),
 email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', unit_id INTEGER NOT NULL DEFAULT 1,
 active INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS points (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
 unit_id INTEGER NOT NULL DEFAULT 1,
 lat REAL NOT NULL, lon REAL NOT NULL,
 capacity_kg REAL NOT NULL CHECK(capacity_kg > 0),
 stock_kg REAL NOT NULL CHECK(stock_kg >= 0 AND stock_kg <= capacity_kg),
 estimated_pickup_min INTEGER NOT NULL DEFAULT 10,
 updated_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS stock_history (
 id INTEGER PRIMARY KEY, point_id INTEGER NOT NULL REFERENCES points(id),
 stock_kg REAL NOT NULL, recorded_at TEXT NOT NULL,
 user_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS geocode_cache (
 query TEXT PRIMARY KEY, result_json TEXT NOT NULL, cached_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS missions (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned'
 CHECK(status IN ('planned','in_progress','completed')),
 created_at TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id),
 routing_mode TEXT NOT NULL, distance_km REAL NOT NULL,
 drive_minutes REAL, total_minutes REAL, geometry_json TEXT NOT NULL,
 algorithm TEXT NOT NULL DEFAULT 'nearest-neighbor-2opt',
 assigned_to INTEGER REFERENCES users(id), unit_id INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS mission_stops (
 id INTEGER PRIMARY KEY, mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
 point_id INTEGER NOT NULL REFERENCES points(id), position INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','visited','skipped')),
 planned_stock_kg REAL NOT NULL, collected_kg REAL,
 visited_at TEXT, UNIQUE(mission_id, point_id)
);
CREATE INDEX IF NOT EXISTS idx_stock_history_recorded_at ON stock_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_stock_history_point_recorded ON stock_history(point_id,recorded_at);
CREATE INDEX IF NOT EXISTS idx_mission_stops_status_visited ON mission_stops(status,visited_at);
CREATE TABLE IF NOT EXISTS point_donation_stock (
 point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
 category TEXT NOT NULL, stock_kg REAL NOT NULL DEFAULT 0 CHECK(stock_kg >= 0),
 PRIMARY KEY(point_id,category)
);
CREATE TABLE IF NOT EXISTS donation_stock_history (
 id INTEGER PRIMARY KEY, point_id INTEGER NOT NULL REFERENCES points(id),
 category TEXT NOT NULL, stock_kg REAL NOT NULL CHECK(stock_kg >= 0),
 recorded_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS mission_stop_donations (
 id INTEGER PRIMARY KEY, mission_stop_id INTEGER NOT NULL REFERENCES mission_stops(id) ON DELETE CASCADE,
 category TEXT NOT NULL, collected_kg REAL NOT NULL CHECK(collected_kg >= 0),
 UNIQUE(mission_stop_id,category)
);
CREATE INDEX IF NOT EXISTS idx_donation_stock_history_recorded ON donation_stock_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_mission_stop_donations_category ON mission_stop_donations(category);
"""


def initialize(path=None, admin_username=None, admin_password=None):
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        seed_local_units(db)
        _ensure_column(db, "users", "email", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(db, "users", "phone", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(db, "users", "unit_id", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(db, "points", "unit_id", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(db, "missions", "unit_id", "INTEGER NOT NULL DEFAULT 1")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(lower(email)) WHERE email<>''")
        _migrate_donation_categories(db)
        mission_columns = {row[1] for row in db.execute("PRAGMA table_info(missions)")}
        if "algorithm" not in mission_columns:
            db.execute("ALTER TABLE missions ADD COLUMN algorithm TEXT NOT NULL DEFAULT 'nearest-neighbor-2opt'")
        user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        if "session_version" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
        defaults = {
            "unit_name": "Croix-Rouge Calais",
            "depot_address": "57 Rue Magenta, 62100 Calais, France",
            "depot_lat": "50.946834",
            "depot_lon": "1.859344",
            "demo_data": "1",
        }
        for key, value in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (key, value))
            db.execute("INSERT OR IGNORE INTO unit_settings(unit_id,key,value) VALUES (1,?,?)", (key, value))
        if admin_username and admin_password:
            db.execute(
                "INSERT INTO users(username,name,password_hash,role) VALUES (?,?,?,'coordinator')",
                (admin_username, admin_username, generate_password_hash(admin_password)),
            )
        if db.execute("SELECT COUNT(*) FROM points").fetchone()[0] == 0:
            csv_path = ROOT / "data" / "collection_points.csv"
            with csv_path.open(newline="", encoding="utf-8") as file:
                for row in csv.DictReader(file):
                    if row["Store_Name"] == "Croix-Rouge Calais":
                        continue
                    capacity = float(row["Max_Capacity"]) / 1000
                    stock = float(row["Current_Stock"]) / 1000
                    db.execute(
                        """INSERT INTO points(name,address,lat,lon,capacity_kg,stock_kg,
                           estimated_pickup_min,updated_at) VALUES (?,?,?,?,?,?,?,?)""",
                        (row["Store_Name"], row["Address"], float(row["Latitude"]),
                         float(row["Longitude"]), capacity, stock, 10, now()),
                    )
        _migrate_donation_categories(db)
        db.commit()


def migrate_existing(path=None):
    db_path = Path(path or os.getenv("DATABASE_PATH", DEFAULT_DB))
    if not db_path.exists():
        return
    with closing(connect(db_path)) as db, db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "points" in tables:
            db.execute("CREATE TABLE IF NOT EXISTS local_units (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, source_url TEXT NOT NULL, postal_code TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '')")
            db.execute("CREATE TABLE IF NOT EXISTS unit_settings (unit_id INTEGER NOT NULL REFERENCES local_units(id), key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(unit_id,key))")
            seed_local_units(db)
            for table, column, definition in (("users","email","TEXT NOT NULL DEFAULT ''"),("users","phone","TEXT NOT NULL DEFAULT ''"),("users","unit_id","INTEGER NOT NULL DEFAULT 1"),("points","unit_id","INTEGER NOT NULL DEFAULT 1"),("missions","unit_id","INTEGER NOT NULL DEFAULT 1")):
                if table in tables:
                    _ensure_column(db, table, column, definition)
            if "users" in tables:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(lower(email)) WHERE email<>''")
            for key, value in (("unit_name","Croix-Rouge Calais"),("depot_address","57 Rue Magenta, 62100 Calais, France"),("depot_lat","50.946834"),("depot_lon","1.859344"),("demo_data","1")):
                db.execute("INSERT OR IGNORE INTO unit_settings(unit_id,key,value) SELECT 1,key,value FROM settings WHERE key=?", (key,))
            db.execute("""CREATE TABLE IF NOT EXISTS geocode_cache (
                query TEXT PRIMARY KEY, result_json TEXT NOT NULL, cached_at TEXT NOT NULL
            )""")
        if "missions" in tables:
            columns = {row[1] for row in db.execute("PRAGMA table_info(missions)")}
            if "algorithm" not in columns:
                db.execute("ALTER TABLE missions ADD COLUMN algorithm TEXT NOT NULL DEFAULT 'nearest-neighbor-2opt'")
        if "users" in tables:
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "session_version" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
        if "stock_history" in tables:
            db.execute("CREATE INDEX IF NOT EXISTS idx_stock_history_recorded_at ON stock_history(recorded_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_stock_history_point_recorded ON stock_history(point_id,recorded_at)")
        if "mission_stops" in tables:
            db.execute("CREATE INDEX IF NOT EXISTS idx_mission_stops_status_visited ON mission_stops(status,visited_at)")
        _migrate_donation_categories(db)


def _ensure_column(db, table, column, definition):
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_local_units(db):
    path = ROOT / "data" / "local_units.json"
    if path.exists():
        units = json.loads(path.read_text(encoding="utf-8"))["units"]
    else:
        units = [{"slug":"unite-locale-de-calais","name":"Unité locale de Calais", "source_url":"https://www.croix-rouge.fr/unite-locale-de-calais", "postal_code":"62100", "city":"Calais"}]
    db.executemany("INSERT OR IGNORE INTO local_units(slug,name,source_url,postal_code,city) VALUES (:slug,:name,:source_url,:postal_code,:city)", units)


def _migrate_donation_categories(db):
    """Preserve legacy aggregate stock in an explicitly unclassified bucket."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS point_donation_stock (
      point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
      category TEXT NOT NULL, stock_kg REAL NOT NULL DEFAULT 0 CHECK(stock_kg >= 0),
      PRIMARY KEY(point_id,category));
    CREATE TABLE IF NOT EXISTS donation_stock_history (
      id INTEGER PRIMARY KEY, point_id INTEGER NOT NULL REFERENCES points(id), category TEXT NOT NULL,
      stock_kg REAL NOT NULL CHECK(stock_kg >= 0), recorded_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS mission_stop_donations (
      id INTEGER PRIMARY KEY, mission_stop_id INTEGER NOT NULL REFERENCES mission_stops(id) ON DELETE CASCADE,
      category TEXT NOT NULL, collected_kg REAL NOT NULL CHECK(collected_kg >= 0),
      UNIQUE(mission_stop_id,category));
    CREATE INDEX IF NOT EXISTS idx_donation_stock_history_recorded ON donation_stock_history(recorded_at);
    CREATE INDEX IF NOT EXISTS idx_mission_stop_donations_category ON mission_stop_donations(category);
    """)
    db.execute("""INSERT OR IGNORE INTO point_donation_stock(point_id,category,stock_kg)
                  SELECT id,'unclassified',stock_kg FROM points""")


def point_dict(row):
    point = dict(row)
    point["fill_pct"] = round(100 * point["stock_kg"] / point["capacity_kg"], 1)
    return point


def points(db, active_only=True, unit_id=1):
    query = "SELECT * FROM points WHERE unit_id=?" + (" AND active=1" if active_only else "") + " ORDER BY name"
    result = [point_dict(row) for row in db.execute(query, (unit_id,))]
    for point in result:
        point["donations"] = {row["category"]: row["stock_kg"] for row in db.execute(
            "SELECT category,stock_kg FROM point_donation_stock WHERE point_id=?", (point["id"],)
        )}
    return result


def depot(db, unit_id=1):
    settings = dict(db.execute("SELECT key,value FROM settings").fetchall())
    settings.update(dict(db.execute("SELECT key,value FROM unit_settings WHERE unit_id=?", (unit_id,)).fetchall()))
    return {
        "name": settings["unit_name"], "address": settings["depot_address"],
        "lat": float(settings["depot_lat"]), "lon": float(settings["depot_lon"]),
    }
