import logging
import os
import asyncio
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.websockets import WebSocketDisconnect

from models.database import TrafficDB
from models.user import User
from webapp.auth import AuthError, AuthService
from webapp.async_persistence import AsyncPersistenceService
from webapp.persistence import PersistenceService
from webapp.settings_service import SettingsService
from utils.app_config import SETTINGS
from webapp.runtime import LANES, TrafficRuntime
from webapp.schemas import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ReportCreateRequest,
    RegisterRequest,
    SettingsUpdateRequest,
    VerifyEmailRequest,
    WebRTCOfferRequest,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)


def _require_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def _require_admin(request: Request):
    user = _require_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def _safe_local_evidence_path(image_url: str) -> Path | None:
    candidate = Path(image_url)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    allowed_roots = [
        (Path.cwd() / "assets" / "web_evidence").resolve(),
        (Path.cwd() / "screenshots" / "violations").resolve(),
    ]
    for root in allowed_roots:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    return None


def _stream_settings_payload() -> dict:
    return {
        "browser_capture_fps": float(SETTINGS.get("browser_capture_fps", 20.0)),
        "stream_output_fps": float(SETTINGS.get("stream_output_fps", 20.0)),
        "browser_stream_jpeg_quality": float(SETTINGS.get("browser_stream_jpeg_quality", 0.6)),
        "browser_stream_width": int(SETTINGS.get("browser_stream_width", 640)),
        "browser_stream_height": int(SETTINGS.get("browser_stream_height", 480)),
        "phone_capture_mode": str(SETTINGS.get("phone_capture_mode", "canvas_jpeg")),
    }


def _page_context(request: Request, title: str, **extra) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    context = {
        "request": request,
        "title": title,
        "user": user,
        "lanes": LANES,
    }
    context.update(extra)
    return context


def create_app() -> FastAPI:
    app = FastAPI(title="SystemOptiflow Web", version="2.0.0")
    app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    db = TrafficDB()
    persistence = PersistenceService(db)
    async_persistence = AsyncPersistenceService(persistence)
    auth_service = AuthService(db, persistence)
    runtime = TrafficRuntime(async_persistence)
    settings_service = SettingsService()

    app.state.db = db
    app.state.persistence = persistence
    app.state.async_persistence = async_persistence
    app.state.auth_service = auth_service
    app.state.runtime = runtime
    app.state.settings_service = settings_service

    @app.on_event("startup")
    async def _startup():
        if os.getenv("OPTIFLOW_SKIP_RUNTIME_STARTUP") == "1":
            logger.info("Skipping runtime startup due to OPTIFLOW_SKIP_RUNTIME_STARTUP=1")
            return
        runtime.set_event_loop(asyncio.get_event_loop())
        runtime.start()

    @app.on_event("shutdown")
    async def _shutdown():
        runtime.stop()

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        target = "/dashboard" if request.session.get("user") else "/login"
        return RedirectResponse(url=target, status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if request.session.get("user"):
            return RedirectResponse(url="/dashboard", status_code=303)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "title": "SystemOptiflow Login",
                "demo_username": os.getenv("DEMO_USERNAME", "admin"),
            },
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse(
            "dashboard.html",
            _page_context(request, "SystemOptiflow Dashboard"),
        )

    @app.get("/health")
    async def health():
        camera_rt = runtime.camera_runtime
        cameras = {
            lane: camera_rt.status(lane) if camera_rt else "unknown"
            for lane in LANES
        }
        return {
            "status": "ok" if not runtime.runtime_error else "degraded",
            "runtime_error": runtime.runtime_error,
            "db_connected": persistence.is_connected(),
            "cameras": cameras,
        }

    @app.post("/api/auth/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...)):
        try:
            user = auth_service.authenticate(username, password)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        request.session["user"] = {
            "user_id": user.get("user_id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role", "operator"),
        }
        return {"ok": True, "user": request.session["user"]}

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    @app.post("/api/auth/register")
    async def register(payload: RegisterRequest):
        try:
            return auth_service.register_user(**payload.model_dump())
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/auth/verify-email")
    async def verify_email(payload: VerifyEmailRequest):
        try:
            return auth_service.verify_registration(payload.email, payload.code)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/auth/request-password-reset")
    async def request_password_reset(payload: PasswordResetRequest):
        try:
            return auth_service.request_password_reset(payload.username, payload.email)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/auth/reset-password")
    async def reset_password(payload: PasswordResetConfirmRequest):
        try:
            return auth_service.reset_password(payload.email, payload.code, payload.new_password)
        except AuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/cameras")
    async def cameras(request: Request):
        _require_user(request)
        snapshot = runtime.snapshot()
        return {
            "cameras": [
                {
                    "lane": lane,
                    "source": snapshot["lanes"][lane]["source"],
                    "status": snapshot["lanes"][lane]["camera_status"],
                }
                for lane in LANES
            ]
        }

    @app.get("/api/status")
    async def status(request: Request):
        _require_user(request)
        return runtime.snapshot()

    @app.get("/api/violations")
    async def violations(request: Request, limit: int = 50):
        _require_user(request)
        return {"items": persistence.list_violations(limit=limit)}

    @app.delete("/api/violations")
    async def clear_violations(request: Request):
        _require_admin(request)
        return {"ok": persistence.clear_violations()}

    @app.get("/api/accidents")
    async def accidents(request: Request, limit: int = 50):
        _require_user(request)
        return {"items": persistence.list_accidents(limit=limit)}

    @app.delete("/api/accidents")
    async def clear_accidents(request: Request):
        _require_admin(request)
        return {"ok": persistence.clear_accidents()}

    @app.get("/api/reports")
    async def reports(request: Request, limit: int = 50):
        _require_user(request)
        return {"items": persistence.list_reports(limit=limit)}

    @app.post("/api/reports")
    async def create_report(request: Request, payload: ReportCreateRequest):
        user = _require_user(request)
        item = persistence.create_report(
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            author_id=user.get("user_id"),
            author_name=user.get("username", "Anonymous"),
        )
        return {"item": item}

    @app.get("/api/reports/{report_id}")
    async def get_report(request: Request, report_id: str):
        _require_user(request)
        item = persistence.get_report(report_id)
        if not item:
            raise HTTPException(status_code=404, detail="Report not found.")
        return {"item": item}

    @app.get("/api/settings")
    async def get_settings(request: Request):
        _require_user(request)
        return {"settings": settings_service.current()}

    @app.put("/api/settings")
    async def update_settings(request: Request, payload: SettingsUpdateRequest):
        _require_user(request)
        return {"settings": settings_service.apply(payload.settings)}

    @app.get("/api/admin/users")
    async def list_admin_users(request: Request):
        _require_admin(request)
        return {"items": db.get_all_users() if db else []}

    @app.post("/api/admin/users")
    async def create_admin_user(request: Request, payload: AdminUserCreateRequest):
        _require_admin(request)
        user_id, error = db.create_user(
            first_name="",
            last_name="",
            username=payload.username,
            email=payload.email,
            password_hash=User.hash_password(payload.password),
            role=payload.role,
        )
        if not user_id:
            raise HTTPException(status_code=400, detail=error or "Failed to create user.")
        user = db.get_user_by_id(user_id)
        return {"item": user}

    @app.patch("/api/admin/users/{user_id}")
    async def update_admin_user(request: Request, user_id: str, payload: AdminUserUpdateRequest):
        _require_admin(request)
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        ok = db.update_user(user_id, **updates)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to update user.")
        return {"item": db.get_user_by_id(user_id)}

    @app.delete("/api/admin/users/{user_id}")
    async def delete_admin_user(request: Request, user_id: str):
        _require_admin(request)
        ok = db.delete_user(user_id)
        if not ok:
            raise HTTPException(status_code=400, detail="Failed to delete user.")
        return {"ok": True}

    @app.get("/api/streams/health")
    async def stream_health():
        """Per-lane stream status. No auth required for monitoring tools."""
        camera_rt = runtime.camera_runtime
        return {
            lane: {
                "status": camera_rt.status(lane) if camera_rt else "unknown",
                "stale": (
                    camera_rt.managers[lane].is_stale(15.0)
                    if camera_rt and lane in camera_rt.managers
                    else False
                ),
                "source": SETTINGS.get(f"camera_source_{lane}", "Simulated"),
            }
            for lane in LANES
        }

    @app.post("/api/streams/{lane}/restart")
    async def restart_stream(request: Request, lane: str):
        """Release a camera connection and let sync_sources() reconnect it on the next tick."""
        _require_user(request)
        if lane not in LANES:
            raise HTTPException(status_code=404, detail="Unknown lane.")
        camera_rt = runtime.camera_runtime
        if not camera_rt:
            raise HTTPException(status_code=503, detail="Runtime not initialised.")
        manager = camera_rt.managers.pop(lane, None)
        if manager:
            manager.release()
        camera_rt.last_attempt_at[lane] = 0.0
        camera_rt._reconnect_backoff[lane] = 5.0
        return {"ok": True, "lane": lane}

    @app.get("/api/streams/{lane}.mjpeg")
    async def mjpeg_stream(request: Request, lane: str):
        _require_user(request)
        if lane not in LANES:
            raise HTTPException(status_code=404, detail="Unknown lane.")

        async def generator():
            boundary = b"--frame\r\n"
            last_ts = 0.0
            while True:
                if await request.is_disconnected():
                    logger.debug(f"MJPEG client disconnected from lane {lane}")
                    break
                frame, ts = runtime.mjpeg_frame_with_ts(lane)
                if frame and ts > last_ts:
                    last_ts = ts
                    yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                output_fps = max(5.0, min(30.0, float(SETTINGS.get("stream_output_fps", 20.0))))
                await asyncio.sleep(1.0 / output_fps)

        return StreamingResponse(generator(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/violations/{violation_id}/image")
    async def violation_image(request: Request, violation_id: str):
        _require_user(request)
        items = persistence.list_violations(limit=500)
        item = next((entry for entry in items if entry.get("violation_id") == violation_id), None)
        if not item or not item.get("image_url"):
            raise HTTPException(status_code=404, detail="Violation image not found.")
        image_url = item["image_url"]
        if image_url.startswith(("http://", "https://")):
            return RedirectResponse(url=image_url, status_code=307)
        local_path = _safe_local_evidence_path(image_url)
        if not local_path or not local_path.exists():
            raise HTTPException(status_code=404, detail="Violation image file is unavailable.")
        return FileResponse(local_path)

    @app.get("/violations", response_class=HTMLResponse)
    async def violations_page(request: Request):
        return templates.TemplateResponse(
            "violations.html",
            _page_context(request, "Violations · SystemOptiflow"),
        )

    @app.get("/reports", response_class=HTMLResponse)
    async def reports_page(request: Request):
        return templates.TemplateResponse(
            "reports.html",
            _page_context(request, "Issue Reports · SystemOptiflow"),
        )

    @app.get("/incidents", response_class=HTMLResponse)
    async def incidents_page(request: Request):
        return templates.TemplateResponse(
            "incidents.html",
            _page_context(request, "Incident History · SystemOptiflow"),
        )

    @app.get("/traffic-reports", response_class=HTMLResponse)
    async def traffic_reports_page(request: Request):
        return templates.TemplateResponse(
            "traffic_reports.html",
            _page_context(request, "Traffic Reports · SystemOptiflow"),
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse(
            "settings.html",
            _page_context(request, "Settings · SystemOptiflow"),
        )

    @app.get("/stream", response_class=HTMLResponse)
    async def stream_page(request: Request):
        return templates.TemplateResponse(
            "stream.html",
            {
                **_page_context(request, "Phone Camera Stream"),
                "stream_settings": _stream_settings_payload(),
            },
        )

    @app.websocket("/ws/stream/{lane}")
    async def stream_ws(websocket: WebSocket, lane: str):
        if lane not in LANES:
            await websocket.close(code=1008)
            return
        user = websocket.session.get("user")
        if not user:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        settings_service.apply({f"camera_source_{lane}": "Browser"}, persist=False)
        runtime.set_browser_mode(lane, "canvas")
        try:
            while True:
                data = await websocket.receive_bytes()
                runtime.inject_browser_frame(lane, data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            settings_service.apply({f"camera_source_{lane}": "Simulated"}, persist=False)
            runtime.set_browser_mode(lane, None)
            runtime.browser_frames[lane] = None

    @app.websocket("/ws/view/{lane}")
    async def view_ws(websocket: WebSocket, lane: str):
        if lane not in LANES:
            await websocket.close(code=1008)
            return
        user = websocket.session.get("user")
        if not user:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=3)
        runtime.register_viewer(lane, queue)
        try:
            while True:
                frame = await queue.get()
                await websocket.send_bytes(frame)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            runtime.unregister_viewer(lane, queue)

    @app.websocket("/ws/dashboard")
    async def dashboard_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(runtime.snapshot())
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return

    # ── WebRTC signalling endpoints ────────────────────────────────────────────

    @app.get("/api/webrtc/ice-config")
    async def webrtc_ice_config(request: Request):
        """Return ICE server list (STUN + TURN credentials) for the phone browser."""
        _require_user(request)
        vps_ip = os.getenv("VPS_PUBLIC_IP", "")
        turn_user = os.getenv("TURN_USERNAME", "optiflow")
        turn_pass = os.getenv("TURN_PASSWORD", "changeme")
        ice_servers = [{"urls": "stun:stun.l.google.com:19302"}]
        if vps_ip:
            ice_servers.append({
                "urls": f"turn:{vps_ip}:3478",
                "username": turn_user,
                "credential": turn_pass,
            })
        return JSONResponse({"iceServers": ice_servers})

    @app.post("/api/webrtc/offer/{lane}")
    async def webrtc_offer(request: Request, lane: str, body: WebRTCOfferRequest):
        """SDP exchange: accept a WebRTC offer from the phone and return an answer."""
        _require_user(request)
        if lane not in LANES:
            raise HTTPException(status_code=404, detail="Unknown lane.")
        if body.type != "offer":
            raise HTTPException(status_code=400, detail="SDP type must be 'offer'.")

        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription
        except ImportError:
            raise HTTPException(status_code=501, detail="aiortc is not installed on this server.")

        pc = RTCPeerConnection()
        track_task: asyncio.Task = None

        @pc.on("track")
        def on_track(track):
            nonlocal track_task
            if track.kind == "video":
                track_task = asyncio.ensure_future(runtime.inject_webrtc_track(lane, track))
                runtime.set_browser_mode(lane, "webrtc")

        @pc.on("connectionstatechange")
        async def on_connection_state_change():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                if track_task and not track_task.done():
                    track_task.cancel()
                settings_service.apply({f"camera_source_{lane}": "Simulated"}, persist=False)
                runtime.set_browser_mode(lane, None)
                runtime.browser_frames[lane] = None
                await pc.close()

        await pc.setRemoteDescription(RTCSessionDescription(sdp=body.sdp, type=body.type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        settings_service.apply({f"camera_source_{lane}": "Browser"}, persist=False)

        return JSONResponse({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if exc.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
