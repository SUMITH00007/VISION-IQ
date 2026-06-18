# Real-Time Object Detection Application  

VISION IQ 

This repository contains a modular, fully-functional, real-time object detection application in Python. It captures video from a webcam or a local video file, runs object detection using a YOLOv8 pre-trained model (via Ultralytics), overlays BGR color-coded bounding boxes and class labels, displays performance metrics (rolling average FPS), and supports saving the annotated output stream.

---

## Features
- **YOLOv8 Inference Wrapper**: Safely loads model files and manages execution target device (CPU/GPU).
- **Performance-Adaptive Processing**: Features an adaptive frame skipping mechanism that automatically stabilizes visual frame rate on lower-end devices by reusing bounding boxes from the last inference step if the detector cannot keep up with the webcam rate.
- **Dynamic Overlays**: Color-codes bounding boxes and text labels by class ID from a curated color palette. Renders real-time rolling-average FPS and active model parameters inside transparent overlays.
- **Controls**: Pause/resume control freeze-frames the screen, minimizing camera consumption.
- **Output Recording**: Streamlines output writing to MP4/AVI formats.

---

## Project Structure
```text
object_detection/
├── main.py            # Entry point, webcam capture loop, and CLI argument orchestration
├── detector.py        # Detector class encapsulating YOLOv8 inference and runtime controls
├── utils.py           # Aspect-ratio resizing, FPS calculation, and visual drawing overlays
├── config.py          # Application-wide constants (YOLO settings, COCO classes, and UI colors)
├── requirements.txt   # Pinpoint package dependencies
└── README.md          # Setup, usage guide, and troubleshooting instructions
```

---

## Installation

### Prerequisites
- Python 3.10 or higher.
- A functional webcam or video file.

### Steps
1. Navigate to the project directory:
   ```bash
   cd object_detection
   ```

2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   # On Windows (PowerShell/CMD)
   .\venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Installing `ultralytics` will automatically install dependencies like PyTorch (`torch`) and NumPy (`numpy`).*

---

## Usage Guide

You can run the application as a Command Line Interface (CLI) or as a Web Dashboard.

### Web Dashboard (Local Mode)
To launch the interactive Web Dashboard locally, use the `--web` flag:
```bash
python main.py --web
```
Once started, open your browser and navigate to:
- **Dashboard**: `http://127.0.0.1:8000`
- **Detection Page**: `http://127.0.0.1:8000/detect`

### Cloud Deployment (e.g. Render)
The application is fully optimized for cloud platforms like Render. In cloud mode, because the server has no physical camera attached:
1. It automatically requests the user's camera permission in the browser.
2. The browser streams frames to the server using standard secure HTTPS requests.
3. The server processes frames using a warm pre-loaded model, drawing neon detection overlays back onto the live video overlay in real-time.

To run/deploy the web server in cloud mode manually, use:
```bash
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

### Basic CLI Run
Start the command-line application with default settings (webcam source `0`, model `yolov8n.pt`, confidence threshold `0.5`, resized width `640` pixels, CPU/GPU auto-detection):
```bash
python main.py
```

### Run Options Examples

- **Detect Only Specific Classes (e.g. People=0, Cars=2)**:
  ```bash
  python main.py --classes 0 2
  ```

- **Force CUDA (GPU) Execution**:
  ```bash
  python main.py --device cuda
  ```

- **Record and Save Annotated Feed to Video File**:
  ```bash
  # Saves as AVI
  python main.py --save output.avi
  # Saves as MP4
  python main.py --save output.mp4
  ```

- **Use a Video File as Input Source**:
  ```bash
  python main.py --source /path/to/video.mp4
  ```

- **Run Headless (Useful with `--save` on servers without displays)**:
  ```bash
  python main.py --no-display --save output.mp4
  ```

- **Adjust Parameters at Launch**:
  ```bash
  python main.py --model yolov8s.pt --conf 0.65 --width 800
  ```

---

## Keyboard Controls
When the visual display window is active:
- **`p`**: Pause/resume the application feed (freezes camera capture and display).
- **`q`**: Quit and safely release all resources.

---

## Troubleshooting

### 1. Camera Index Not Found or Already in Use
- **Symptoms**: CLI outputs `CRITICAL ERROR: Could not open video source '0'.`
- **Solutions**:
  - Verify that your camera is plugged in and recognized by your operating system.
  - Close other applications that might be using the camera (e.g. Zoom, MS Teams, Skype).
  - If you have multiple webcams, try using a different index (e.g., `--source 1` or `--source 2`).

### 2. Model Download Fails or Hangs
- **Symptoms**: CLI hangs at YOLO startup or prints network connection exceptions.
- **Solutions**:
  - Ensure you have an active internet connection on the first run; the application needs to download `yolov8n.pt` from the Ultralytics assets server.
  - If you are behind a corporate proxy, set the `HTTP_PROXY` and `HTTPS_PROXY` environment variables in your terminal.
  - Alternatively, download `yolov8n.pt` manually from the [Ultralytics Releases Page](https://github.com/ultralytics/assets/releases) and place it directly in the `object_detection` directory, then run the command again.

### 3. CUDA Not Available Warning
- **Symptoms**: Terminal displays: `WARNING: CUDA device requested but PyTorch CUDA support is not available. Falling back to CPU execution.`
- **Solutions**:
  - The default `pip install` may download the CPU-only version of PyTorch. To run on GPU, install the CUDA-supported version of PyTorch from the official [PyTorch Website](https://pytorch.org/).
  - Example installation command for Windows/Linux with CUDA 11.8:
    ```bash
    pip install torch --extra-index-url https://download.pytorch.org/whl/cu118
    ```
  - Verify CUDA support in your Python environment:
    ```bash
    python -c "import torch; print(torch.cuda.is_available())"
    ```
#
