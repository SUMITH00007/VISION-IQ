"""FastAPI web server — dual-thread grab/infer, MJPEG stream, IP camera support."""

import os
import base64
import uuid
import threading
import time
import cv2
import numpy as np
from contextlib import asynccontextmanager
from typing import Any, Optional, Generator
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from detector import Detector
from utils import FPSCounter, draw_boxes, draw_fps, resize_frame, draw_active_tallies
from config import DEFAULT_MODEL, DEFAULT_CONF

# ── Cloud Mode Globals ────────────────────────────────────────────────────────
cloud_detector: Optional[Detector] = None
cloud_conf: float = DEFAULT_CONF


@asynccontextmanager
async def _lifespan(app_instance: FastAPI):
    """Pre-load YOLO model in cloud mode (Render) where start_server() is never called."""
    global cloud_detector
    if processor is None:
        print("[cloud] Pre-loading YOLO model for cloud deployment...")
        try:
            cloud_detector = Detector(DEFAULT_MODEL, DEFAULT_CONF, "cpu")
            print("[cloud] Model loaded successfully.")
        except Exception as e:
            print(f"[cloud] ERROR: Could not pre-load model: {e}")
    yield
    cloud_detector = None


# ── App Setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="VisionIQ", lifespan=_lifespan)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
if "VERCEL" in os.environ:
    OUTPUTS_DIR = "/tmp/outputs"
else:
    OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

try:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create outputs directory {OUTPUTS_DIR}: {e}")

try:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create templates directory {TEMPLATES_DIR}: {e}")

app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
STATIC_DIR = os.path.join(BASE_DIR, "static")
try:
    os.makedirs(STATIC_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create static directory {STATIC_DIR}: {e}")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

processor: Optional["VideoProcessor"] = None


# ── Video Processor ───────────────────────────────────────────────────────────
class VideoProcessor:
    """
    Two-thread design:
      grab_thread  – reads camera frames at full camera speed.
      infer_thread – runs detection and encodes JPEG.
    The MJPEG endpoint always serves the newest annotated JPEG.

    FPS optimisations:
      • INTER_NEAREST resize (fastest)
      • JPEG quality 62 (balance speed / quality)
      • Minimal lock scope — never hold locks during encode/detect
      • _source_changed flag forces cap release+reopen instantly
    """

    JPEG_QUALITY = 62   # 55-70 is sweet spot for CPU streaming

    def __init__(self, source: Any, model_path: str, conf: float,
                 device: str, width: int) -> None:
        self.source      = source
        self.model_path  = model_path
        self.conf        = conf
        self.device      = device
        self.width       = width
        self.paused      = True

        # Apply OpenCV optimizations
        cv2.setUseOptimized(True)
        cv2.setNumThreads(4)

        # Use 480 resolution for fast CPU inference while maintaining detection accuracy
        self.imgsz = 480

        self.detector    = Detector(model_path, conf, device, imgsz=self.imgsz)
        self.fps_counter = FPSCounter(window_size=30)

        # Tracking and line counting setup
        from utils import TrackTracker
        self.tracker      = TrackTracker()
        self.enable_tracking = False
        self.draw_line    = False
        self.line_pos     = 0.5
        self.line_dir     = "horizontal"

        self._raw_frame:      Optional[np.ndarray] = None
        self._annotated_jpeg: Optional[bytes]      = None
        self._detections:     list[dict[str, Any]] = []
        self._fps:            float = 0.0
        self._inf_ms:         float = 0.0
        self._cap_ok:         bool  = False
        self._grab_count:     int   = 0

        self._frame_lock   = threading.Lock()
        self._result_lock  = threading.Lock()
        self._running      = False
        self._annotated_ready = threading.Event()

        # ── IP camera fix: explicit flag so grab_loop always reopens ──
        self._source_changed = threading.Event()
        self._release_thread: Optional[threading.Thread] = None

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._grab_loop,  daemon=True, name="grab").start()
        threading.Thread(target=self._infer_loop, daemon=True, name="infer").start()
        threading.Thread(target=self._stream_loop, daemon=True, name="stream").start()

    def stop(self) -> None:
        self._running = False

    def _safe_release(self, cap_to_release: cv2.VideoCapture) -> None:
        """Safely release the Capture object in a background thread."""
        try:
            print("[proc] Releasing video capture handle...")
            cap_to_release.release()
            print("[proc] Video capture handle released.")
        except Exception as e:
            print(f"[proc] Error during video capture release: {e}")

    def _trigger_async_release(self, cap_to_release: cv2.VideoCapture) -> None:
        """Triggers background release, joining the previous thread with a timeout first."""
        if cap_to_release is None:
            return
        if self._release_thread and self._release_thread.is_alive():
            print("[proc] Joining previous release thread...")
            self._release_thread.join(timeout=1.5)
        self._release_thread = threading.Thread(
            target=self._safe_release,
            args=(cap_to_release,),
            daemon=True,
            name="cap_release"
        )
        self._release_thread.start()

    def restart_source(self, source: Any) -> None:
        """Hot-swap the camera source. Signals grab_loop to release+reopen."""
        print(f"[proc] Source change → {source!r}")
        self.source = source
        self._cap_ok = False
        self._source_changed.set()   # wake up grab_loop immediately

    def switch_model(self, model_name: str) -> None:
        """Dynamically hot-swaps the active YOLO model in the detector."""
        print(f"[proc] Dynamic model switch requested: {self.model_path} ──> {model_name}")
        if self.model_path == model_name:
            return
        
        t0 = time.perf_counter()
        self.imgsz = self.imgsz  # preserve current imgsz setting
        # Instantiate outside the result lock to keep streaming alive during initialization
        new_detector = Detector(model_name, self.conf, self.device, imgsz=self.imgsz)
        
        with self._result_lock:
            self.detector = new_detector
            self.model_path = model_name
            
        duration = (time.perf_counter() - t0) * 1000.0
        print(f"[proc] Successfully hot-swapped model to: {model_name} in {duration:.1f} ms")

    def set_conf(self, conf: float) -> None:
        self.conf = conf
        self.detector.set_conf(conf)

    def set_imgsz(self, imgsz: int) -> None:
        self.imgsz = imgsz
        self.detector.imgsz = imgsz

    def set_iou(self, iou: float) -> None:
        self.detector.set_iou(iou)

    def set_augment(self, augment: bool) -> None:
        self.detector.set_augment(augment)

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._result_lock:
            return self._annotated_jpeg

    def get_stats(self) -> dict:
        with self._result_lock:
            counts: dict[str, int] = {}
            for d in self._detections:
                name = d["class_name"]
                counts[name] = counts.get(name, 0) + 1
            cross_counts = {}
            if self.enable_tracking and hasattr(self.tracker, "counts"):
                cross_counts = {cls: {"in": d["in"], "out": d["out"]} for cls, d in self.tracker.counts.items()}
            return {
                "fps":               round(self._fps, 1),
                "inf_ms":            round(self._inf_ms),
                "source":            str(self.source),
                "cap_ok":            self._cap_ok,
                "conf":              self.conf,
                "imgsz":             self.imgsz,
                "augment":           self.detector.augment,
                "iou":               self.detector.nms_iou,
                "active_detections": counts,
                "enable_tracking":   self.enable_tracking,
                "draw_line":         self.draw_line,
                "line_pos":          self.line_pos,
                "line_dir":          self.line_dir,
                "cross_counts":      cross_counts,
            }

    # ── Grab Thread ────────────────────────────────────────────────────────────
    def _grab_loop(self) -> None:
        cap: Optional[cv2.VideoCapture] = None

        while self._running:
            # ── Handle paused state ──
            if self.paused:
                if cap is not None:
                    # Async release using safe thread management
                    self._trigger_async_release(cap)
                    cap = None
                    self._cap_ok = False
                time.sleep(0.08)
                continue

            # ── Source changed — force release and reopen ──
            if self._source_changed.is_set():
                self._source_changed.clear()
                if cap is not None:
                    # Async release using safe thread management
                    self._trigger_async_release(cap)
                    cap = None
                self._cap_ok = False

            # ── (Re-)open capture ──
            if cap is None or not cap.isOpened():
                # Wait for any previous background release thread to finish before opening a new cap
                if self._release_thread and self._release_thread.is_alive():
                    print("[grab] Waiting for previous release thread to complete before opening new source...")
                    self._release_thread.join(timeout=1.5)

                src = self.source
                print(f"[grab] Opening source: {src!r}")

                # Build a proper OpenCV source string/int
                is_network = isinstance(src, str) and (
                    src.startswith("http://")
                    or src.startswith("https://")
                    or src.startswith("rtsp://")
                )
                if is_network:
                    # Set FFMPEG ultra-low-latency flags
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                        "rtsp_transport;udp"
                        "|fflags;nobuffer+discardcorrupt"
                        "|analyzeduration;0"
                        "|probesize;32"
                        "|max_delay;0"
                        "|stimeout;2000000"
                        "|timeout;2000000"
                        "|reorder_queue_size;0"
                    )
                    cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                    if not cap.isOpened():
                        # Retry without explicit backend
                        self._trigger_async_release(cap)
                        cap = cv2.VideoCapture(src)
                else:
                    # Try to convert to int if it's a digit string (e.g. "0")
                    if isinstance(src, str) and src.isdigit():
                        src = int(src)

                    if isinstance(src, int):
                        import platform
                        if platform.system() == "Windows":
                            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
                        else:
                            cap = cv2.VideoCapture(src)
                        if cap.isOpened():
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                            cap.set(cv2.CAP_PROP_FPS, 30)
                    else:
                        cap = cv2.VideoCapture(str(src))

                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    self._cap_ok = True
                    print(f"[grab] Opened OK: {src!r}")
                else:
                    print(f"[grab] Cannot open {src!r}. Retrying in 3 s…")
                    self._cap_ok = False
                    if cap:
                        self._trigger_async_release(cap)
                    cap = None
                    time.sleep(3)
                    continue

            # ── Read frame — drain buffer for network streams ──
            is_net_src = isinstance(self.source, str) and (
                "http" in str(self.source) or "rtsp" in str(self.source)
            )
            if is_net_src:
                # Drain: grab() in tight loop to skip buffered frames,
                # then retrieve() only the very latest one
                grabbed = False
                for _ in range(30):  # cap at 30 to avoid infinite spin
                    if not cap.grab():
                        break
                    grabbed = True
                if not grabbed:
                    print(f"[grab] Grab failed — source may have disconnected.")
                    self._cap_ok = False
                    if cap:
                        self._trigger_async_release(cap)
                    cap = None
                    time.sleep(1)
                    continue
                ret, frame = cap.retrieve()
            else:
                ret, frame = cap.read()
            if not ret:
                print(f"[grab] Read failed — source may have disconnected.")
                self._cap_ok = False
                if cap:
                    self._trigger_async_release(cap)
                cap = None
                time.sleep(1)
                continue

            # Un-mirror webcam feed — local cameras (integer sources) are
            # often horizontally flipped by default on Windows/DirectShow.
            if isinstance(self.source, int):
                frame = cv2.flip(frame, 1)

            self._grab_count += 1
            with self._frame_lock:
                self._raw_frame = frame

    # ── Inference Thread ────────────────────────────────────────────────────────
    def _infer_loop(self) -> None:
        last_grab_count = -1

        while self._running:
            if self.paused:
                time.sleep(0.05)
                continue

            # Grab latest frame (minimal lock)
            with self._frame_lock:
                frame      = self._raw_frame
                grab_count = self._grab_count

            if frame is None or grab_count == last_grab_count:
                time.sleep(0.004)
                continue

            last_grab_count = grab_count

            # ── Resize to inference resolution (imgsz) ──
            h, w = frame.shape[:2]
            imgsz = self.imgsz if self.imgsz > 0 else 640
            if w != imgsz:
                nh = int(h * imgsz / w)
                # Use nearest-neighbor interpolation for fastest inference resize (YOLO handles it fine)
                small = cv2.resize(frame, (imgsz, nh), interpolation=cv2.INTER_NEAREST)
            else:
                nh = h
                small = frame

            t0 = time.perf_counter()
            detections = self.detector.detect(small, track=self.enable_tracking)
            inf_ms = (time.perf_counter() - t0) * 1000.0

            # Scale detections back to display width and height accurately
            disp_w = self.width if self.width > 0 else w
            disp_h = int(h * disp_w / w)
            scale_x = disp_w / imgsz
            scale_y = disp_h / nh
            mapped_detections = []
            for d in detections:
                bbox = d["bbox"]
                mapped_bbox = [
                    int(bbox[0] * scale_x),
                    int(bbox[1] * scale_y),
                    int(bbox[2] * scale_x),
                    int(bbox[3] * scale_y)
                ]
                mapped_polygon = None
                if d.get("polygon") is not None:
                    mapped_polygon = [[int(pt[0] * scale_x), int(pt[1] * scale_y)] for pt in d["polygon"]]

                mapped_detections.append({
                    "class_id": d["class_id"],
                    "class_name": d["class_name"],
                    "confidence": d["confidence"],
                    "bbox": mapped_bbox,
                    "track_id": d["track_id"],
                    "polygon": mapped_polygon
                })

            with self._result_lock:
                self._detections = mapped_detections
                self._inf_ms = inf_ms
                self._infer_frame = frame
                self._infer_grab_count = grab_count

    # ── Stream Loop Thread (Decoupled rendering for high-FPS video) ─────────────
    def _stream_loop(self) -> None:
        enc_params = [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_QUALITY]
        last_grab_count = -1

        while self._running:
            if self.paused:
                time.sleep(0.05)
                continue

            with self._frame_lock:
                frame      = self._raw_frame
                grab_count = self._grab_count

            if frame is None or grab_count == last_grab_count:
                time.sleep(0.01)  # Match display feed rate
                continue

            last_grab_count = grab_count
            with self._result_lock:
                dets       = self._detections

            # Resize to display resolution
            h, w = frame.shape[:2]
            disp_w = self.width if self.width > 0 else w
            if w != disp_w:
                nh = int(h * disp_w / w)
                # Use bilinear interpolation for smooth and high-quality display output
                disp_frame = cv2.resize(frame, (disp_w, nh), interpolation=cv2.INTER_LINEAR)
            else:
                disp_frame = frame.copy()

            # Annotate
            if self.enable_tracking:
                h_disp, w_disp = disp_frame.shape[:2]
                self.tracker.update(dets, self.line_pos, self.line_dir, w_disp, h_disp)
                ann = draw_boxes(
                    disp_frame, dets,
                    tracker=self.tracker,
                    line_pos=self.line_pos,
                    line_dir=self.line_dir,
                    draw_line=self.draw_line
                )
            else:
                ann = draw_boxes(disp_frame, dets, tracker=None, draw_line=False)
            ann = draw_active_tallies(ann, dets)
            self.fps_counter.update()
            fps = self.fps_counter.get_fps()
            ann = draw_fps(ann, fps)

            # Encode
            ok, jpeg_buf = cv2.imencode(".jpg", ann, enc_params)

            if ok:
                with self._result_lock:
                    self._annotated_jpeg = jpeg_buf.tobytes()
                    self._fps = fps
                self._annotated_ready.set()

            # Throttle thread slightly to save CPU cycles (~60 FPS max)
            time.sleep(0.005)


# ── MJPEG stream ──────────────────────────────────────────────────────────────
def _stream_gen() -> Generator[bytes, None, None]:
    """Yields MJPEG frames instantly via thread events for ultra-low latency."""
    while True:
        if processor:
            # Wait for next frame. Short timeout lets us check if processor stopped.
            if processor._annotated_ready.wait(timeout=0.1):
                processor._annotated_ready.clear()
                frame = processor.get_latest_jpeg()
                if frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        else:
            time.sleep(0.05)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if processor:
        processor.paused = True
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": processor.get_stats() if processor else {}}
    )


@app.get("/detect", response_class=HTMLResponse)
async def detect_page(request: Request):
    if processor:
        processor.paused = False
    cfg = {
        "conf":   processor.conf   if processor else DEFAULT_CONF,
        "source": processor.source if processor else 0,
        "model":  processor.model_path if processor else DEFAULT_MODEL,
    }
    return templates.TemplateResponse(
        request=request,
        name="detect.html",
        context={"config": cfg}
    )


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        _stream_gen(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


class ConfigUpdate(BaseModel):
    conf:            Optional[float] = None
    source:          Optional[str]   = None
    paused:          Optional[bool]  = None
    model:           Optional[str]   = None
    enable_tracking: Optional[bool]  = None
    draw_line:       Optional[bool]  = None
    line_pos:        Optional[float] = None
    line_dir:        Optional[str]   = None
    world_classes:   Optional[str]   = None
    imgsz:           Optional[int]   = None
    augment:         Optional[bool]  = None
    iou:             Optional[float] = None
    width:           Optional[int]   = None


@app.post("/api/config")
async def set_config(cfg: ConfigUpdate):
    global cloud_conf
    if not processor:
        # ── Cloud mode: update cloud detector settings ──
        if cloud_detector is None:
            return JSONResponse({"error": "No detector available"}, status_code=500)
        if cfg.conf is not None:
            cloud_conf = max(0.05, min(0.95, cfg.conf))
            cloud_detector.set_conf(cloud_conf)
        if cfg.iou is not None:
            cloud_detector.set_iou(max(0.05, min(0.95, cfg.iou)))
        if cfg.augment is not None:
            cloud_detector.set_augment(cfg.augment)
        if cfg.imgsz is not None:
            cloud_detector.imgsz = cfg.imgsz
        return {
            "status": "ok", "conf": cloud_detector.conf_threshold,
            "source": "browser", "model": DEFAULT_MODEL,
            "enable_tracking": False, "draw_line": False,
            "line_pos": 0.5, "line_dir": "horizontal",
            "imgsz": cloud_detector.imgsz, "augment": cloud_detector.augment,
            "iou": cloud_detector.nms_iou, "width": 640, "mode": "cloud"
        }

    if cfg.conf is not None:
        processor.set_conf(max(0.05, min(0.95, cfg.conf)))

    if cfg.imgsz is not None:
        processor.set_imgsz(cfg.imgsz)

    if cfg.augment is not None:
        processor.set_augment(cfg.augment)

    if cfg.iou is not None:
        processor.set_iou(max(0.05, min(0.95, cfg.iou)))

    if cfg.width is not None:
        processor.width = cfg.width

    if cfg.source is not None:
        raw = cfg.source.strip()
        # Automatically prepend http:// if missing but it looks like a network address
        if not (raw.startswith("http://") or raw.startswith("https://") or raw.startswith("rtsp://")):
            if "." in raw and (":" in raw or "/" in raw):
                raw = "http://" + raw

        # Force http:// instead of https:// for standard local IP cameras (HTTPS fails TLS handshakes)
        if raw.startswith("https://"):
            if "192.168." in raw or "10." in raw or "172." in raw or ":8080" in raw:
                raw = raw.replace("https://", "http://")

        # URL-based sources (IP / mobile cameras)
        if (raw.startswith("http://") or raw.startswith("https://")
                or raw.startswith("rtsp://")):
            # If standard IP Webcam port 8080 is specified but path is empty, auto-append /videofeed
            if ":8080" in raw:
                import urllib.parse
                try:
                    parsed = urllib.parse.urlparse(raw)
                    if not parsed.path or parsed.path == "/":
                        raw = urllib.parse.urljoin(raw, "/videofeed")
                except Exception:
                    pass

            # Auto-rewrite standard IP Webcam endpoints to high-FPS MJPEG stream
            if "video" in raw and not raw.endswith("videofeed"):
                if raw.endswith("/video"):
                    raw = raw.replace("/video", "/videofeed")
            processor.restart_source(raw)
        else:
            try:
                processor.restart_source(int(raw))
            except ValueError:
                processor.restart_source(raw)

    if cfg.paused is not None:
        if cfg.paused:
            processor.paused = True
        else:
            processor.paused = False

    if cfg.enable_tracking is not None:
        processor.enable_tracking = cfg.enable_tracking
        if not cfg.enable_tracking and hasattr(processor.tracker, "reset_counts"):
            processor.tracker.reset_counts()

    if cfg.draw_line is not None:
        processor.draw_line = cfg.draw_line

    if cfg.line_pos is not None:
        processor.line_pos = max(0.05, min(0.95, cfg.line_pos))

    if cfg.line_dir is not None:
        processor.line_dir = cfg.line_dir

    if cfg.world_classes is not None:
        classes_list = [c.strip() for c in cfg.world_classes.split(",") if c.strip()]
        if classes_list and hasattr(processor.detector, "update_world_classes"):
            processor.detector.update_world_classes(classes_list)

    if cfg.model is not None:
        model_name = cfg.model.strip()
        valid_models = {
            "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8s-seg.pt", "yolov8s-worldv2.pt",
            "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11s-seg.pt"
        }
        if model_name in valid_models:
            processor.switch_model(model_name)

    return {
        "status": "ok", 
        "conf": processor.conf, 
        "source": str(processor.source),
        "model": processor.model_path,
        "enable_tracking": processor.enable_tracking,
        "draw_line": processor.draw_line,
        "line_pos": processor.line_pos,
        "line_dir": processor.line_dir,
        "imgsz": processor.imgsz,
        "augment": processor.detector.augment,
        "iou": processor.detector.nms_iou,
        "width": processor.width
    }


@app.post("/api/reset_counts")
async def reset_counts():
    if processor and hasattr(processor.tracker, "reset_counts"):
        processor.tracker.reset_counts()
        return {"status": "ok"}
    return JSONResponse({"error": "No processor or tracker running"}, status_code=500)


@app.get("/api/stats")
async def get_stats():
    if processor:
        stats = processor.get_stats()
        stats["mode"] = "local"
        return stats
    # Cloud mode: return sensible defaults
    return {
        "fps": 0, "inf_ms": 0, "source": "browser", "cap_ok": False,
        "conf": cloud_conf,
        "imgsz": cloud_detector.imgsz if cloud_detector else 640,
        "augment": cloud_detector.augment if cloud_detector else False,
        "iou": cloud_detector.nms_iou if cloud_detector else 0.45,
        "active_detections": {}, "enable_tracking": False,
        "draw_line": False, "line_pos": 0.5, "line_dir": "horizontal",
        "cross_counts": {}, "mode": "cloud"
    }


@app.post("/api/detect_frame")
async def detect_frame(file: UploadFile = File(...)):
    """Accept a JPEG frame from the browser camera, run YOLO, return boxes."""
    det = processor.detector if processor else cloud_detector
    if det is None:
        return JSONResponse({"error": "No detector available"}, status_code=500)

    img_bytes = await file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse({"error": "Could not decode image"}, status_code=400)

    h, w = img.shape[:2]
    t0 = time.perf_counter()
    detections = det.detect(img, track=False, imgsz=640)
    inf_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "detections": [
            {"bbox": d["bbox"], "class_name": d["class_name"],
             "confidence": d["confidence"]}
            for d in detections
        ],
        "width": w, "height": h, "inf_ms": round(inf_ms, 1),
    }


# ── Capture ───────────────────────────────────────────────────────────────────
def _make_counts(dets: list) -> tuple[dict, bool]:
    counts: dict[str, int] = {}
    for d in dets:
        name = d["class_name"]
        counts[name] = counts.get(name, 0) + 1
    return counts, False


@app.post("/api/capture")
async def capture_frame():
    if not processor:
        return JSONResponse(
            {"error": "Cloud mode — use the Capture button (browser frame is sent to /api/upload)."},
            status_code=400,
        )

    frame = None
    with processor._frame_lock:
        if processor._raw_frame is not None:
            frame = processor._raw_frame.copy()

    if frame is None:
        return JSONResponse(
            {"error": "No frame available — is the camera connected?"},
            status_code=503,
        )

    uid      = str(uuid.uuid4())
    out_path = os.path.join(OUTPUTS_DIR, f"capture_{uid}.jpg")

    h, w = frame.shape[:2]
    max_size = 1280
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        nw = int(w * scale)
        nh = int(h * scale)
        img_to_detect = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    else:
        img_to_detect = frame

    dets  = processor.detector.detect(img_to_detect, track=False, imgsz=640)

    # Extract crops from clean img_to_detect
    crops = []
    ch, cw = img_to_detect.shape[:2]
    for i, d in enumerate(dets):
        bbox = d["bbox"]
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(cw, x2)
        y2 = min(ch, y2)
        if x2 > x1 and y2 > y1:
            crop_img = img_to_detect[y1:y2, x1:x2]
            crop_filename = f"crop_{uid}_{i}_{d['class_name']}.jpg"
            crop_path = os.path.join(OUTPUTS_DIR, crop_filename)
            cv2.imwrite(crop_path, crop_img)
            crops.append({
                "class_name": d["class_name"],
                "confidence": d["confidence"],
                "url": f"/outputs/{crop_filename}"
            })

    ann   = draw_boxes(img_to_detect, dets, tracker=None, draw_line=False)
    ann   = draw_active_tallies(ann, dets)
    cv2.imwrite(out_path, ann)

    counts, has_low = _make_counts(dets)
    return {
        "type":               "capture",
        "detections":         len(dets),
        "classes":            counts,
        "url":                f"/outputs/capture_{uid}.jpg",
        "confidence_warning": has_low,
        "crops":              crops,
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    ext      = os.path.splitext(file.filename or "")[1].lower()
    uid      = str(uuid.uuid4())
    in_path  = os.path.join(OUTPUTS_DIR, f"in_{uid}{ext}")
    is_img   = ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    is_vid   = ext in (".mp4", ".avi", ".mov", ".mkv")
    out_ext  = ".jpg" if is_img else ".mp4"
    out_path = os.path.join(OUTPUTS_DIR, f"out_{uid}{out_ext}")

    with open(in_path, "wb") as f:
        f.write(await file.read())

    if not (is_img or is_vid):
        os.remove(in_path)
        return JSONResponse({"error": "Unsupported file type"}, status_code=400)

    det = processor.detector if processor else (cloud_detector if cloud_detector else Detector(DEFAULT_MODEL, DEFAULT_CONF, "cpu"))

    if is_img:
        img = cv2.imread(in_path)
        if img is None:
            os.remove(in_path)
            return JSONResponse({"error": "Cannot read image"}, status_code=400)
        ih, iw = img.shape[:2]
        max_size = 1280
        if max(ih, iw) > max_size:
            scale = max_size / max(ih, iw)
            nw = int(iw * scale)
            nh = int(ih * scale)
            img_to_detect = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        else:
            img_to_detect = img
        dets  = det.detect(img_to_detect, track=False, imgsz=640)

        # Extract crops from clean img_to_detect
        crops = []
        dh, dw = img_to_detect.shape[:2]
        for i, d in enumerate(dets):
            bbox = d["bbox"]
            x1, y1, x2, y2 = bbox
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(dw, x2)
            y2 = min(dh, y2)
            if x2 > x1 and y2 > y1:
                crop_img = img_to_detect[y1:y2, x1:x2]
                crop_filename = f"crop_{uid}_{i}_{d['class_name']}.jpg"
                crop_path = os.path.join(OUTPUTS_DIR, crop_filename)
                cv2.imwrite(crop_path, crop_img)
                crops.append({
                    "class_name": d["class_name"],
                    "confidence": d["confidence"],
                    "url": f"/outputs/{crop_filename}"
                })

        ann   = draw_boxes(img_to_detect, dets, tracker=None, draw_line=False)
        ann   = draw_active_tallies(ann, dets)
        cv2.imwrite(out_path, ann)
        try:
            os.remove(in_path)
        except Exception:
            pass
        counts, has_low = _make_counts(dets)
        return {
            "type": "image", "detections": len(dets),
            "classes": counts, "confidence_warning": has_low,
            "url": f"/outputs/out_{uid}.jpg",
            "crops": crops
        }

    else:  # video
        w = 640
        cap    = cv2.VideoCapture(in_path)
        fps_v  = cap.get(cv2.CAP_PROP_FPS) or 20.0
        src_w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_h  = int(src_h * w / max(src_w, 1))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps_v, (w, out_h))
        n = 0
        while n < 300:
            ret, frame = cap.read()
            if not ret:
                break
            fh, fw = frame.shape[:2]
            nh = int(fh * w / fw)
            # Use bilinear interpolation for smooth resizing to preserve edge/localization detail
            small = cv2.resize(frame, (w, nh), interpolation=cv2.INTER_LINEAR)
            dets  = det.detect(small, track=False)
            ann   = draw_boxes(small, dets, tracker=None, draw_line=False)
            ann   = draw_active_tallies(ann, dets)
            writer.write(ann)
            n += 1
        cap.release()
        writer.release()
        try:
            os.remove(in_path)
        except Exception:
            pass
        return {"type": "video", "frames": n, "url": f"/outputs/out_{uid}.mp4"}


# ── Server Entry Point ────────────────────────────────────────────────────────
def start_server(model_path: str, conf: float, device: str,
                 width: int, source: Any, port: int = 8000) -> None:
    global processor
    processor = VideoProcessor(source, model_path, conf, device, width)
    processor.start()

    import uvicorn
    print(f"\n🚀  Dashboard  →  http://127.0.0.1:{port}")
    print(f"🔍  Detection  →  http://127.0.0.1:{port}/detect\n")
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    finally:
        processor.stop()
