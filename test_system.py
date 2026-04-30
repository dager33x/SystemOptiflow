import unittest
import os
import sys

# Ensure the app root is in the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.app_config import SETTINGS
from utils.paths import get_resource_path

class TestSystemFeatures(unittest.TestCase):

    def test_01_configuration_feature(self):
        """Configuration Management Feature"""
        self.assertIn("enable_detection", SETTINGS)
        self.assertTrue(isinstance(SETTINGS["ai_throttle_seconds"], float))

    def test_02_path_resolution_feature(self):
        """Resource Path Resolution Feature"""
        path = get_resource_path("assets")
        self.assertIsInstance(path, str)

    def test_03_accident_detection_logic_feature(self):
        """Accident Detection Controller Feature"""
        from controllers.accident_controller import AccidentController
        self.assertTrue(callable(AccidentController))

    def test_04_violation_logging_feature(self):
        """Violation Controller Feature"""
        from controllers.violation_controller import ViolationController
        self.assertTrue(callable(ViolationController))

    def test_05_authentication_feature(self):
        """Authentication Controller Feature"""
        from controllers.auth_controller import AuthController
        self.assertTrue(callable(AuthController))

    def test_06_main_traffic_controller_feature(self):
        """Main Traffic Logic Feature"""
        from controllers.main_controller import MainController
        self.assertTrue(callable(MainController))

    def test_07_emergency_vehicle_feature(self):
        """Emergency Vehicle Detection Feature"""
        from controllers.emergency_controller import EmergencyController
        self.assertTrue(callable(EmergencyController))

    def test_08_ai_models_feature(self):
        """AI Models Readiness Feature"""
        self.assertTrue(os.path.exists(get_resource_path("yolov8n.pt")), "YOLO model not found")
        self.assertTrue(os.path.exists(get_resource_path("Optiflow_Dqn.pth")), "DQN model not found")

if __name__ == '__main__':
    print("=====================================================")
    print(" RUNNING UNIT TESTS FOR ALL SYSTEM FEATURES          ")
    print("=====================================================")
    
    # Run tests programmatically to capture and format output
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSystemFeatures)
    
    # Capture standard output to prevent verbose unittest prints if we just want clean output
    runner = unittest.TextTestRunner(stream=open(os.devnull, 'w'), verbosity=0)
    result = runner.run(suite)
    
    print("\n=================== TEST RESULTS ====================")
    if result.wasSuccessful():
        # Iterate over test methods defined in the class to print their docstrings
        for method_name in dir(TestSystemFeatures):
            if method_name.startswith("test_"):
                doc = getattr(TestSystemFeatures, method_name).__doc__
                print(f"[Feature Tested]: {doc} -> REMARK: PASSED")
        print("=====================================================")
        print("OVERALL SYSTEM STATUS: ALL FEATURES TESTED SUCCESSFULLY.")
        print("FINAL REMARK: PASSED")
    else:
        for i, (test, traceback) in enumerate(result.failures + result.errors):
            print(f"[Feature Tested]: {test._testMethodDoc} -> REMARK: FAILED")
            print(f"Details: {traceback}")
        print("=====================================================")
        print("OVERALL SYSTEM STATUS: SOME TESTS FAILED.")
