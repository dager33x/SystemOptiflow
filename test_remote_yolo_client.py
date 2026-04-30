import json
import unittest
from unittest.mock import patch

import numpy as np

from detection.remote_yolo_client import RemoteYoloClient, RemoteYoloSettings


class _FakeHttpResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class TestRemoteYoloClient(unittest.TestCase):
    def _enabled_client(self, token="secret"):
        return RemoteYoloClient(
            settings=RemoteYoloSettings(
                enabled=True,
                endpoint_url="https://example.modal.run",
                token=token,
                timeout_seconds=2.0,
                enabled_lanes=frozenset({"all"}),
            )
        )

    def test_all_lane_setting_allows_any_lane(self):
        client = self._enabled_client()

        self.assertTrue(client.is_enabled_for_lane("north"))
        self.assertTrue(client.is_enabled_for_lane("south"))
        self.assertTrue(client.is_enabled_for_lane("east"))
        self.assertTrue(client.is_enabled_for_lane("west"))

    def test_specific_lane_setting_only_allows_configured_lanes(self):
        client = RemoteYoloClient(
            settings=RemoteYoloSettings(
                enabled=True,
                endpoint_url="https://example.modal.run",
                token="secret",
                timeout_seconds=2.0,
                enabled_lanes=frozenset({"north", "east"}),
            )
        )

        self.assertTrue(client.is_enabled_for_lane("north"))
        self.assertTrue(client.is_enabled_for_lane("east"))
        self.assertFalse(client.is_enabled_for_lane("south"))
        self.assertFalse(client.is_enabled_for_lane("west"))

    def test_successful_response_maps_to_optiflow_detection_shape(self):
        client = self._enabled_client()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        modal_payload = {
            "ok": True,
            "detections": [
                {
                    "class_id": 1,
                    "class_name": "car",
                    "confidence": 0.91,
                    "bbox": [10.2, 20.8, 60.1, 80.9],
                    "center": [35.1, 50.4],
                }
            ],
            "inference_ms": 12.5,
            "image_shape": {"height": 100, "width": 200},
        }

        with patch(
            "detection.remote_yolo_client.urllib.request.urlopen",
            return_value=_FakeHttpResponse(modal_payload),
        ) as urlopen_mock:
            result = client.detect(frame, lane_id="north")

        self.assertIsNotNone(result)
        self.assertTrue(result["success"])
        self.assertEqual(12.5, result["remote_inference_ms"])
        self.assertEqual(
            [
                {
                    "class_id": 1,
                    "class_name": "car",
                    "confidence": 0.91,
                    "bbox": (10, 21, 60, 81),
                    "center": (35, 50),
                    "source": "remote_modal",
                }
            ],
            result["detections"],
        )

        request = urlopen_mock.call_args.args[0]
        self.assertEqual("POST", request.get_method())
        self.assertEqual("secret", request.headers["X-optiflow-token"])

    def test_disabled_client_returns_none_without_http_call(self):
        client = RemoteYoloClient(
            settings=RemoteYoloSettings(
                enabled=False,
                endpoint_url="https://example.modal.run",
                token="secret",
                timeout_seconds=2.0,
                enabled_lanes=frozenset({"all"}),
            )
        )
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        with patch("detection.remote_yolo_client.urllib.request.urlopen") as urlopen_mock:
            result = client.detect(frame)

        self.assertIsNone(result)
        urlopen_mock.assert_not_called()

    def test_missing_url_returns_none_without_http_call(self):
        client = RemoteYoloClient(
            settings=RemoteYoloSettings(
                enabled=True,
                endpoint_url="",
                token="secret",
                timeout_seconds=2.0,
                enabled_lanes=frozenset({"all"}),
            )
        )
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        with patch("detection.remote_yolo_client.urllib.request.urlopen") as urlopen_mock:
            result = client.detect(frame)

        self.assertIsNone(result)
        urlopen_mock.assert_not_called()

    def test_http_failure_returns_none_for_local_fallback(self):
        client = self._enabled_client()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        with patch(
            "detection.remote_yolo_client.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = client.detect(frame, lane_id="north")

        self.assertIsNone(result)

    def test_bad_json_returns_none_for_local_fallback(self):
        client = self._enabled_client()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        with patch(
            "detection.remote_yolo_client.urllib.request.urlopen",
            return_value=_FakeHttpResponse(b"not-json"),
        ):
            result = client.detect(frame, lane_id="north")

        self.assertIsNone(result)

    def test_modal_failure_response_returns_none_for_local_fallback(self):
        client = self._enabled_client()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        with patch(
            "detection.remote_yolo_client.urllib.request.urlopen",
            return_value=_FakeHttpResponse({"ok": False, "error": "decode failed"}),
        ):
            result = client.detect(frame, lane_id="north")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
