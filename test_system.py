import importlib.util
import os
import unittest

from utils.app_config import SETTINGS
from utils.paths import get_resource_path


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
    def test_06_login_page_renders(self):
        os.environ["OPTIFLOW_SKIP_RUNTIME_STARTUP"] = "1"
        from fastapi.testclient import TestClient
        from webapp.main import create_app

        with TestClient(create_app()) as client:
            response = client.get("/login")
            self.assertEqual(response.status_code, 200)
            self.assertIn("SystemOptiflow", response.text)


if __name__ == "__main__":
    unittest.main()
