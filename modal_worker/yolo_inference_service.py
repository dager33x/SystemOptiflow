import os
import time
from typing import Any

import modal
from fastapi import File, Header, HTTPException, UploadFile

MODEL_PATH = "/root/models/best.pt"
API_TOKEN_ENV = "OPTIFLOW_MODAL_TOKEN"
GPU_TYPE = "A10"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi[standard]",
        "ultralytics",
        "opencv-python-headless",
        "numpy",
        "pillow",
    )
    .add_local_file("best.pt", MODEL_PATH)
)

app = modal.App("optiflow-yolo-inference", image=image)


@app.cls(
    gpu=GPU_TYPE,
    timeout=60,
    scaledown_window=300,
    secrets=[modal.Secret.from_name("optiflow-modal-token")],
)
class YoloInferenceService:
    @modal.enter()
    def load_model(self) -> None:
        from ultralytics import YOLO

        self.model = YOLO(MODEL_PATH)

    def _detect_bytes(self, image_bytes: bytes) -> dict[str, Any]:
        import cv2
        import numpy as np

        started_at = time.perf_counter()

        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if frame is None:
            return {
                "ok": False,
                "error": "Could not decode image bytes.",
                "detections": [],
                "inference_ms": 0.0,
            }

        results = self.model(frame, verbose=False)[0]

        detections = []
        names = results.names

        for box in results.boxes:
            class_id = int(box.cls[0])
            class_name = names.get(class_id, str(class_id))
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]

            detections.append(
                {
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [x1, y1, x2, y2],
                    "center": [(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                }
            )

        inference_ms = (time.perf_counter() - started_at) * 1000.0

        return {
            "ok": True,
            "detections": detections,
            "inference_ms": inference_ms,
            "image_shape": {
                "height": int(frame.shape[0]),
                "width": int(frame.shape[1]),
            },
        }

    @modal.fastapi_endpoint(method="POST", docs=True)
    async def detect(
        self,
        file: UploadFile = File(...),
        x_optiflow_token: str | None = Header(default=None),
    ):
        expected_token = os.environ.get(API_TOKEN_ENV)

        if expected_token and x_optiflow_token != expected_token:
            raise HTTPException(status_code=401, detail="Invalid Optiflow token.")

        image_bytes = await file.read()

        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty image upload.")

        return self._detect_bytes(image_bytes)
