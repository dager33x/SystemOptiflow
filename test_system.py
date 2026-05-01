import importlib.util
import os
import unittest

from utils.app_config import SETTINGS
from utils.paths import get_resource_path

os.environ.setdefault("SESSION_SECRET", "test-session-secret")


FASTAPI_AVAILABLE = all(
    importlib.util.find_spec(package) is not None
    for package in ("fastapi", "itsdangerous", "jinja2", "email_validator")
)
DESKTOP_AVAILABLE = all(
    importlib.util.find_spec(package) is not None
    for package in ("customtkinter", "cv2")
)


class TestSystemOptiflowWeb(unittest.TestCase):
    def test_01_settings_include_lane_sources(self):
        for lane in ("north", "south", "east", "west"):
            self.assertIn(f"camera_source_{lane}", SETTINGS)

    def test_02_model_assets_exist(self):
        self.assertTrue(os.path.exists(get_resource_path("yolov8n.pt")))
        self.assertTrue(os.path.exists(get_resource_path("best.pt")))
        self.assertTrue(os.path.exists(get_resource_path("Optiflow_Dqn.pth")))

    @unittest.skipUnless(DESKTOP_AVAILABLE, "Desktop UI dependencies are not installed")
    def test_03_desktop_entrypoint_imports(self):
        import app

        self.assertTrue(callable(app.main))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_04_web_server_entrypoint_exports_app(self):
        import web_server

        self.assertIsNotNone(web_server.app)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_05_fastapi_app_starts_without_gui(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("status", payload)
            self.assertIn("db_connected", payload)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_06_create_app_requires_session_secret(self):
        from webapp.main import create_app

        original = os.environ.pop("SESSION_SECRET", None)
        try:
            with self.assertRaises(RuntimeError):
                create_app()
        finally:
            if original is not None:
                os.environ["SESSION_SECRET"] = original

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_07_login_page_renders(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/login")
            self.assertEqual(response.status_code, 200)
            self.assertIn("SystemOptiflow", response.text)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_08_stream_redirect_preserves_lane_target(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/stream?lane=south", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers.get("location"), "/login?next=%2Fstream%3Flane%3Dsouth")

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_09_releases_page_renders_without_auth(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/releases")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Desktop Releases", response.text)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_10_camera_test_accepts_simulated_source(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            login_response = client.post(
                "/api/auth/login",
                data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
            )
            self.assertEqual(login_response.status_code, 200)
            response = client.post("/api/camera-test", json={"lane": "north", "source": "Simulated"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload.get("ok"))
            self.assertEqual(payload.get("lane"), "north")

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_11_camera_test_rejects_invalid_lane(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            login_response = client.post(
                "/api/auth/login",
                data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
            )
            self.assertEqual(login_response.status_code, 200)
            response = client.post("/api/camera-test", json={"lane": "bad-lane", "source": "Simulated"})
            self.assertEqual(response.status_code, 404)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_12_camera_test_rejects_unsafe_source(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            login_response = client.post(
                "/api/auth/login",
                data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
            )
            self.assertEqual(login_response.status_code, 200)
            response = client.post("/api/camera-test", json={"lane": "north", "source": "rtsp://8.8.8.8:554/stream"})
            self.assertEqual(response.status_code, 400)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_13_camera_test_rejects_oversized_source(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            login_response = client.post(
                "/api/auth/login",
                data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
            )
            self.assertEqual(login_response.status_code, 200)
            response = client.post("/api/camera-test", json={"lane": "north", "source": "x" * 513})
            self.assertEqual(response.status_code, 422)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_14_operator_pages_require_auth(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            for path in ("/dashboard", "/violations", "/reports", "/incidents", "/traffic-reports", "/settings", "/stream"):
                response = client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 303, path)
                self.assertTrue(response.headers.get("location", "").startswith("/login?next="), path)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_15_client_config_returns_public_url_and_lanes(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        original_public_url = os.environ.get("PUBLIC_BASE_URL")
        os.environ["PUBLIC_BASE_URL"] = "https://optiflow.example.com"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        try:
            with TestClient(create_app()) as client:
                login_response = client.post(
                    "/api/auth/login",
                    data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
                )
                self.assertEqual(login_response.status_code, 200)
                response = client.get("/api/client-config")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload.get("public_base_url"), "https://optiflow.example.com")
                self.assertEqual(payload.get("lanes"), ["north", "south", "east", "west"])
        finally:
            if original_public_url is None:
                os.environ.pop("PUBLIC_BASE_URL", None)
            else:
                os.environ["PUBLIC_BASE_URL"] = original_public_url

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI dependencies are not installed")
    def test_16_event_ingest_endpoints_accept_authenticated_uploads(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            login_response = client.post(
                "/api/auth/login",
                data={"username": os.getenv("DEMO_USERNAME", "admin"), "password": os.getenv("DEMO_PASSWORD", "admin123")},
            )
            self.assertEqual(login_response.status_code, 200)
            violation = client.post("/api/events/violation", data={"lane": "north", "violation_type": "Red Light Violation"})
            self.assertEqual(violation.status_code, 201)
            accident = client.post(
                "/api/events/accident",
                data={"lane": "south", "severity": "Moderate", "description": "Detected by AI"},
            )
            self.assertEqual(accident.status_code, 201)


if __name__ == "__main__":
    unittest.main()
