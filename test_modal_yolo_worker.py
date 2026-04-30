import pathlib
import unittest


class TestModalYoloWorker(unittest.TestCase):
    def test_web_endpoint_runs_directly_on_gpu_class(self):
        worker_path = pathlib.Path("modal_worker/yolo_inference_service.py")
        source = worker_path.read_text(encoding="utf-8")

        self.assertIn("@app.cls(", source)
        self.assertIn('GPU_TYPE = "A10"', source)
        self.assertIn("gpu=GPU_TYPE", source)
        self.assertIn('secrets=[modal.Secret.from_name("optiflow-modal-token")]', source)
        self.assertIn("@modal.fastapi_endpoint(method=\"POST\", docs=True)", source)
        self.assertIn("async def detect(", source)
        self.assertIn("return self._detect_bytes(image_bytes)", source)
        self.assertNotIn("@app.function", source)
        self.assertNotIn("YoloInferenceService()", source)
        self.assertNotIn(".remote(", source)
        self.assertNotIn(".remote.aio(", source)


if __name__ == "__main__":
    unittest.main()
