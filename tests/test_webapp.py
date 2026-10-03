import os
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import database
import webapp
from webapp import app
from werkzeug.security import generate_password_hash


class WebAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(Path(self.tmp.name) / "test.sqlite3")
        os.environ["ROUTE_SOLVER_SECONDS"] = "1"
        # Keep tests independent from a developer's optional local OSRM service.
        os.environ["ROUTING_URL"] = ""
        database.initialize(admin_username="admin", admin_password="strong-password-123")
        app.config.update(TESTING=True)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["csrf_token"] = "test-token"
        self.headers = {"X-CSRF-Token": "test-token"}

    def tearDown(self):
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("ROUTE_SOLVER_SECONDS", None)
        os.environ.pop("ROUTING_URL", None)
        self.tmp.cleanup()

    def test_demo_import_and_urgent_isolated_point_is_planned(self):
        response = self.client.get("/api/bootstrap")
        self.assertEqual(response.status_code, 200)
        points = response.json["points"]
        self.assertEqual(len(points), 12)
        urgent = [point for point in points if point["fill_pct"] >= 80]
        self.assertEqual(len(urgent), 2)
        response = self.client.post("/api/missions/plan", json={"stop_ids": [point["id"] for point in urgent]}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({point["id"] for point in response.json["stops"]}, {point["id"] for point in urgent})
        self.assertEqual(response.json["routing_mode"], "air")
        self.assertEqual(response.json["geometry"][0], [50.946834, 1.859344])
        self.assertEqual(response.json["geometry"][-1], [50.946834, 1.859344])

    def test_mission_persists_and_stock_updates(self):
        point_id = self.client.get("/api/bootstrap").json["points"][0]["id"]
        created = self.client.post("/api/missions", json={"title": "Tour A", "stop_ids": [point_id]}, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        mission = created.json["mission"]
        self.assertEqual(mission["stops"][0]["point_id"], point_id)
        self.assertEqual(self.client.get(f"/api/missions/{mission['id']}").json["mission"]["title"], "Tour A")
        updated = self.client.patch(f"/api/missions/{mission['id']}/stops/{point_id}", json={"status":"visited","collected_kg":0.5}, headers=self.headers)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["mission"]["status"], "completed")

    def test_donation_categories_track_point_stock_and_mission_collections(self):
        point = self.client.get("/api/bootstrap").json["points"][0]
        point_id = point["id"]
        stock = {category: 0 for category in database.DONATION_CATEGORIES}
        stock.update(clothing=5, hygiene=2)
        saved = self.client.post(f"/api/points/{point_id}/stock", json={"donations": stock}, headers=self.headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["point"]["stock_kg"], 7)
        self.assertEqual(saved.json["point"]["donations"]["clothing"], 5)
        too_much = dict(stock, clothing=point["capacity_kg"] + 1)
        self.assertEqual(self.client.post(f"/api/points/{point_id}/stock", json={"donations": too_much}, headers=self.headers).status_code, 400)

        mission = self.client.post("/api/missions", json={"stop_ids": [point_id]}, headers=self.headers).json["mission"]
        collected = self.client.patch(
            f"/api/missions/{mission['id']}/stops/{point_id}",
            json={"status": "visited", "collected_kg": 1.5,
                  "collected_by_category": {"clothing": 1, "hygiene": 0.5}},
            headers=self.headers,
        )
        self.assertEqual(collected.status_code, 200)
        self.assertEqual(collected.json["mission"]["stops"][0]["collected_by_category"], {"clothing": 1, "hygiene": 0.5})
        export = self.client.get(f"/api/missions/{mission['id']}/export.csv?lang=en")
        self.assertIn(b"Donation breakdown (kg)", export.data)
        self.assertIn(b"clothing: 1; hygiene: 0.5", export.data)
        preview = self.client.get(f"/api/missions/{mission['id']}/email-preview?lang=en")
        self.assertIn("clothing 1 kg", preview.json["body"])
        report = self.client.get("/api/analytics?days=30").json
        totals = {item["category"]: item for item in report["donation_categories"]}
        self.assertEqual(totals["clothing"]["collected_kg"], 1)
        self.assertEqual(totals["hygiene"]["collected_kg"], 0.5)

    def test_auth_csrf_and_invalid_stock(self):
        point_id = self.client.get("/api/bootstrap").json["points"][0]["id"]
        self.assertEqual(self.client.post(f"/api/points/{point_id}/stock", json={"stock_kg": 1}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/points/{point_id}/stock", json={"stock_kg": 999}, headers=self.headers).status_code, 400)
        with app.test_client() as anonymous:
            self.assertEqual(anonymous.get("/api/bootstrap").status_code, 401)

    def test_pages_render(self):
        for path in ("/", "/points", "/planner", "/missions", "/analytics", "/settings"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b"Red Collect", response.data)

    def test_network_analytics_is_available_to_coordinators_only(self):
        report = self.client.get("/api/analytics?days=90")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json["metrics"]["active_points"], 12)
        self.assertEqual(report.json["metrics"]["observations"], 0)
        for days in (30, 90, 180, 365):
            self.assertEqual(self.client.get(f"/api/analytics?days={days}").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics?days=60").status_code, 400)
        self.client.post("/api/users", json={"username":"volunteer","name":"Volunteer",
                          "email":"volunteer@example.org","password":"strong-password-123"}, headers=self.headers)
        with self.client.session_transaction() as session:
            session["user_id"] = 2
        self.assertEqual(self.client.get("/api/analytics").status_code, 403)
        self.assertEqual(self.client.get("/analytics").status_code, 403)

    def test_volunteer_cannot_plan_and_can_complete_stop(self):
        point_id = self.client.get("/api/bootstrap").json["points"][0]["id"]
        with database.connect() as db:
            db.execute("INSERT INTO users(username,name,password_hash,role,email,unit_id) VALUES (?,?,?,'volunteer','helper@example.org',1)",
                       ("volunteer","Volunteer",generate_password_hash("strong-password-123")))
        created = self.client.post("/api/missions", json={"stop_ids":[point_id],"assigned_to":2}, headers=self.headers).json["mission"]
        with self.client.session_transaction() as session:
            session["user_id"] = 2
        self.assertEqual(self.client.post("/api/missions/plan", json={"stop_ids":[point_id]}, headers=self.headers).status_code, 403)
        response = self.client.patch(f"/api/missions/{created['id']}/stops/{point_id}", json={"status":"visited","collected_kg":0.1}, headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_email_preview_and_bilingual_export(self):
        point_id = self.client.get("/api/bootstrap").json["points"][0]["id"]
        mission_id = self.client.post("/api/missions", json={"stop_ids":[point_id]}, headers=self.headers).json["mission"]["id"]
        preview = self.client.get(f"/api/missions/{mission_id}/email-preview?lang=en")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Collection mission", preview.json["subject"])
        exported = self.client.get(f"/api/missions/{mission_id}/export.csv?lang=en")
        self.assertEqual(exported.status_code, 200)
        self.assertIn(b"Planned stock (kg)", exported.data)

    def test_login_form(self):
        with app.test_client() as client:
            page = client.get("/login")
            self.assertEqual(page.status_code, 200)
            with client.session_transaction() as session:
                token = session["csrf_token"]
            logged_in = client.post("/login", data={"username":"admin", "password":"strong-password-123", "csrf_token":token})
            self.assertEqual(logged_in.status_code, 302)
            self.assertEqual(logged_in.headers["Location"], "/")

    def test_signup_assigns_selected_unit_and_profiles_can_be_edited(self):
        with app.test_client() as client:
            client.get("/login")
            with client.session_transaction() as session:
                token=session["csrf_token"]
            with database.connect() as db:
                unit=db.execute("SELECT id FROM local_units WHERE slug='unite-locale-de-calais'").fetchone()[0]
            response=client.post("/signup",data={"csrf_token":token,"username":"new-coord","name":"New Coordinator","email":"coord@example.org","password":"coordinator-pass-123","unit_id":unit})
            self.assertEqual(response.status_code,302)
            with client.session_transaction() as session:
                token=session["csrf_token"]
            edited=client.patch("/api/profile",json={"name":"Coordinator A","email":"coord@example.org","phone":"010203"},headers={"X-CSRF-Token":token})
            self.assertEqual(edited.status_code,200)
            created=client.post("/api/users",json={"username":"helper-a","name":"Helper A","email":"helper-a@example.org","password":"volunteer-pass-123"},headers={"X-CSRF-Token":token})
            self.assertEqual(created.status_code,201)
            with database.connect() as db:
                self.assertEqual(db.execute("SELECT unit_id FROM users WHERE id=?",(created.json["user"]["id"],)).fetchone()[0],unit)

    def test_homepage_offers_signup_and_login(self):
        with app.test_client() as client:
            self.assertEqual(client.get("/").status_code,302)
            page=client.get("/login")
            self.assertIn(b"/signup",page.data)
            self.assertIn("Unité locale de Calais".encode(),page.data)

    def test_unit_data_and_missions_are_not_visible_across_units(self):
        with database.connect() as db:
            other=db.execute("SELECT id FROM local_units WHERE id<>1 LIMIT 1").fetchone()[0]
            db.execute("INSERT INTO points(name,address,unit_id,lat,lon,capacity_kg,stock_kg,updated_at) VALUES ('Private relay','Somewhere',?,48,2,10,5,?)",(other,database.now()))
            db.execute("INSERT INTO users(username,name,password_hash,role,email,unit_id) VALUES ('other-vol','Other Volunteer','hash','volunteer','other@example.org',?)",(other,))
            db.execute("INSERT INTO missions(title,created_at,created_by,routing_mode,distance_km,geometry_json,assigned_to,unit_id) VALUES ('Private mission',? ,1,'air',1,'[]',2,?)",(database.now(),other))
        bootstrap=self.client.get('/api/bootstrap').json
        self.assertNotIn('Private relay',{point['name'] for point in bootstrap['points']})
        self.assertNotIn('Private mission',{mission['title'] for mission in bootstrap['missions']})
        self.assertEqual(self.client.get('/api/missions/1').status_code,404)

    def test_coordinator_can_configure_depot_and_add_volunteer(self):
        changed = self.client.patch("/api/settings", json={"unit_name":"Calais Nord", "depot_lat":50.95}, headers=self.headers)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json["depot"]["name"], "Calais Nord")
        created = self.client.post("/api/users", json={"username":"volunteer2", "name":"Volunteer Two", "email":"volunteer2@example.org", "password":"strong-password-123"}, headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json["user"]["role"], "volunteer")
        self.assertEqual(self.client.post("/api/users", json={"username":"volunteer2", "name":"Duplicate", "email":"volunteer2@example.org", "password":"strong-password-123"}, headers=self.headers).status_code, 409)

    def test_coordinator_can_manage_volunteer_access(self):
        created = self.client.post("/api/users", json={"username":"helper", "name":"Helper", "email":"helper@example.org", "password":"initial-password-123"}, headers=self.headers)
        user_id = created.json["user"]["id"]
        changed = self.client.patch(f"/api/users/{user_id}", json={"name":"Helper One"}, headers=self.headers)
        self.assertEqual(changed.json["user"]["name"], "Helper One")
        reset = self.client.patch(f"/api/users/{user_id}", json={"password":"replacement-pass-123"}, headers=self.headers)
        self.assertEqual(reset.status_code, 200)
        deactivated = self.client.patch(f"/api/users/{user_id}", json={"active":False}, headers=self.headers)
        self.assertEqual(deactivated.json["user"]["active"], 0)
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = user_id
            self.assertEqual(client.get("/api/bootstrap").status_code, 401)

    def test_last_coordinator_cannot_be_deactivated(self):
        result = self.client.patch("/api/users/1", json={"active":False}, headers=self.headers)
        self.assertEqual(result.status_code, 400)

    def test_address_search_is_user_triggered_and_cached(self):
        result = [{"lat":"50.95","lon":"1.86","display_name":"57 Rue Magenta, Calais"}]
        with patch.object(webapp, "urlopen", return_value=io.BytesIO(json.dumps(result).encode())) as request:
            response = self.client.get("/api/geocode?q=57%20Rue%20Magenta&lang=fr")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["results"][0]["lat"], 50.95)
            self.assertEqual(response.json["attribution"], "© OpenStreetMap contributors")
            cached = self.client.get("/api/geocode?q=57%20Rue%20Magenta&lang=fr")
            self.assertEqual(cached.status_code, 200)
            request.assert_called_once()

    def test_existing_database_migrates_address_cache_table(self):
        with database.connect() as db:
            db.execute("DROP TABLE geocode_cache")
            db.execute("DROP INDEX idx_stock_history_recorded_at")
            db.execute("DROP TABLE mission_stop_donations")
            db.execute("DROP TABLE donation_stock_history")
            db.execute("DROP TABLE point_donation_stock")
        database.migrate_existing()
        with database.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            old_stock = db.execute("SELECT stock_kg FROM points WHERE id=1").fetchone()[0]
            migrated_stock = db.execute("SELECT stock_kg FROM point_donation_stock WHERE point_id=1 AND category='unclassified'").fetchone()[0]
        self.assertIn("geocode_cache", tables)
        self.assertIn("idx_stock_history_recorded_at", indexes)
        self.assertEqual(migrated_stock, old_stock)

    def test_route_preview_reports_solver(self):
        point_ids = [item["id"] for item in self.client.get("/api/bootstrap").json["points"][:4]]
        response = self.client.post("/api/missions/plan", json={"stop_ids":point_ids}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json["algorithm"], ("ortools-guided-local-search", "nearest-neighbor-2opt"))


if __name__ == "__main__":
    unittest.main()
