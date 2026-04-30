import pathlib
import unittest


class TestModalYoloWorker(unittest.TestCase):
    def test_async_endpoint_uses_modal_async_remote_call(self):
        worker_path = pathlib.Path("modal_worker/yolo_inference_service.py")
        source = worker_path.read_text(encoding="utf-8")

        self.assertIn("await service.detect_bytes.remote.aio(image_bytes)", source)
        self.assertNotIn("return service.detect_bytes.remote(image_bytes)", source)


if __name__ == "__main__":
    unittest.main()
