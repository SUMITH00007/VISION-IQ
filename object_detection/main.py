"""Main orchestration script for the real-time object detection application.

This script parses command-line arguments, validates devices, opens the video capture stream,
initializes the Detector, runs the capture-inference-draw loop with performance-adaptive
frame skipping, writes output video files if requested, and cleanly releases resources on exit.
"""

import argparse
import os
import sys
import time
from typing import Any, Optional
import cv2

# Absolute imports within project directory
from config import DEFAULT_CONF, DEFAULT_DEVICE, DEFAULT_MODEL
from detector import Detector
from utils import FPSCounter, draw_boxes, draw_fps, draw_info, resize_frame


def parse_source(value: str) -> Any:
    """Parses the video source argument.

    Converts to integer if the input represents a webcam index, otherwise keeps it as a string
    representing a file path.

    Args:
        value: Input string from command-line.

    Returns:
        An integer for a webcam index, or a string for a video file path.
    """
    try:
        return int(value)
    except ValueError:
        return value


def conf_type(value: str) -> float:
    """Validates and parses the confidence threshold argument.

    Args:
        value: Command-line string representation of confidence.

    Returns:
        Confidence value as float.

    Raises:
        argparse.ArgumentTypeError: If value is not a float between 0.0 and 1.0.
    """
    try:
        val = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid float.")

    if not (0.0 <= val <= 1.0):
        raise argparse.ArgumentTypeError(
            f"Confidence threshold must be between 0.0 and 1.0, got {val}"
        )
    return val


def width_type(value: str) -> int:
    """Validates and parses the frame resizing width argument.

    Args:
        value: Command-line string representation of width.

    Returns:
        Width value as integer.

    Raises:
        argparse.ArgumentTypeError: If value is not a positive integer.
    """
    try:
        val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid integer.")

    if val <= 0:
        raise argparse.ArgumentTypeError(f"Width must be a positive integer, got {val}")
    return val


def get_device(requested_device: str) -> str:
    """Checks device hardware availability and falls back to CPU if requested CUDA is unavailable.

    Args:
        requested_device: Hardware device name requested ('cpu', 'cuda', or 'auto').

    Returns:
        Validated device name ('cpu' or 'cuda').
    """
    try:
        import torch

        cuda_available = torch.cuda.is_available()
    except ImportError:
        cuda_available = False

    device_normalized = requested_device.lower()

    if device_normalized == "auto":
        selected = "cuda" if cuda_available else "cpu"
        print(
            f"Device set to 'auto'. Selected: '{selected}' (CUDA available: {cuda_available})"
        )
        return selected

    if device_normalized == "cuda":
        if not cuda_available:
            print(
                "WARNING: CUDA device requested but PyTorch CUDA support is not available."
            )
            print("Falling back to CPU execution.")
            return "cpu"
        return "cuda"

    return device_normalized


def main() -> None:
    """Configures CLI arguments, loads the model, and runs the main webcam processing loop."""
    parser = argparse.ArgumentParser(
        description="Real-Time Object Detection using YOLOv8 and webcam feed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Model name or file path of YOLOv8 model.",
    )
    parser.add_argument(
        "--conf",
        type=conf_type,
        default=DEFAULT_CONF,
        help="Detection confidence threshold (0.0 to 1.0).",
    )
    parser.add_argument(
        "--classes",
        nargs="+",
        type=int,
        default=None,
        help="Space-separated list of COCO class IDs to detect. Default: detect all.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Target execution device ('cpu', 'cuda', or 'auto').",
    )
    parser.add_argument(
        "--source",
        type=parse_source,
        default=0,
        help="Webcam source index (int) or path to input video file (str).",
    )
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="File path to save the annotated video feed.",
    )
    parser.add_argument(
        "--width",
        type=width_type,
        default=640,
        help="Resize frame width for inference/display. Aspect ratio is preserved.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Headless run without opening display window.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch as a FastAPI Web Dashboard instead of desktop window.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the FastAPI web server on.",
    )

    args = parser.parse_args()

    # Validate execution device
    device = get_device(args.device)

    # Launch Web Server if requested
    if args.web:
        try:
            from web_app import start_server
            start_server(
                model_path=args.model,
                conf=args.conf,
                device=device,
                width=args.width,
                source=args.source,
                port=args.port
            )
        except Exception as err:
            print(f"CRITICAL ERROR: Failed to launch web server. Details: {err}")
            sys.exit(1)
        return

    # Instantiate the Detector
    try:
        detector = Detector(
            model_path=args.model, conf_threshold=args.conf, device=device
        )
    except RuntimeError as err:
        print(f"CRITICAL ERROR: {err}")
        sys.exit(1)

    # Set class filter if specified
    if args.classes is not None:
        detector.filter_classes(args.classes)

    # Open video capture stream
    print(f"Opening video source: {args.source}...")
    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        print(f"CRITICAL ERROR: Could not open video source '{args.source}'.")
        print("Please check if the webcam index is valid or if the video file exists.")
        sys.exit(1)

    # Minimize queue latency for webcam sources by using a buffer size of 1
    if isinstance(args.source, int):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Initialize VideoWriter, FPSCounter, and looping states
    writer: Optional[cv2.VideoWriter] = None
    fps_counter = FPSCounter()
    paused = False

    # Metrics for adaptive frame skipping
    last_inference_time = 0.0
    inference_duration = 0.0
    detections: list[dict[str, Any]] = []

    print("\n--- Object Detection Running ---")
    if not args.no_display:
        print("Keyboard Controls:")
        print("  - Press 'p' to PAUSE/RESUME the application feed.")
        print("  - Press 'q' to QUIT the application.")

    try:
        while True:
            # Handle pause state
            if paused:
                if not args.no_display:
                    # Continue displaying the last annotated frame while waiting
                    # Use a small waitKey delay to prevent CPU spinning
                    key = cv2.waitKey(30) & 0xFF
                    if key == ord("q"):
                        break
                    elif key == ord("p"):
                        paused = False
                        print("Application RESUMED.")
                else:
                    # If headless and paused (unusual but possible if controlled via terminal),
                    # sleep briefly
                    time.sleep(0.05)
                continue

            # Read raw frame from stream
            ret, frame = cap.read()
            if not ret:
                # Video file reached the end
                if isinstance(args.source, str):
                    print("End of video file stream reached. Exiting.")
                    break
                # Webcams can occasionally drop a frame mid-stream
                print("Warning: Failed to capture frame from webcam. Skipping frame...")
                continue

            # Record processing tick for FPS calculation
            fps_counter.update()

            # Resize the input frame preserving aspect ratio for faster processing
            processed_frame = resize_frame(frame, args.width)

            # Performance-Adaptive Inference
            current_time = time.perf_counter()
            is_video = isinstance(args.source, str)

            # Run inference if:
            # - We are reading a video file (must process all frames to maintain output integrity)
            # - It's the very first frame
            # - The time elapsed since last inference exceeds the runtime of the last inference
            should_run_inference = (
                is_video
                or (not detections)
                or (current_time - last_inference_time >= inference_duration)
            )

            if should_run_inference:
                inference_start = time.perf_counter()
                detections = detector.detect(processed_frame)
                inference_duration = time.perf_counter() - inference_start
                last_inference_time = inference_start

            # Draw visual overlays
            annotated_frame = draw_boxes(processed_frame, detections)
            fps_val = fps_counter.get_fps()
            annotated_frame = draw_fps(annotated_frame, fps_val)

            model_name = os.path.basename(args.model)
            annotated_frame = draw_info(
                annotated_frame, model_name, detector.conf_threshold
            )

            # Lazy-initialize VideoWriter using the actual resized frame dimensions
            if args.save and writer is None:
                h, w = annotated_frame.shape[:2]
                ext = os.path.splitext(args.save)[1].lower()
                fourcc = (
                    cv2.VideoWriter_fourcc(*"mp4v")
                    if ext == ".mp4"
                    else cv2.VideoWriter_fourcc(*"XVID")
                )

                # Fetch source frame rate or default to 20.0
                fps_out = cap.get(cv2.CAP_PROP_FPS)
                if fps_out <= 0 or fps_out > 100:
                    fps_out = 20.0

                writer = cv2.VideoWriter(args.save, fourcc, fps_out, (w, h))
                if not writer.isOpened():
                    raise RuntimeError(
                        f"Failed to open VideoWriter for saving output to '{args.save}'."
                    )
                print(
                    f"Video recording started. Saving to: {args.save} "
                    f"({fps_out} FPS, size {w}x{h})"
                )

            # Write frame to output video file
            if writer is not None:
                writer.write(annotated_frame)

            # Render frame to GUI window
            if not args.no_display:
                cv2.imshow("Real-Time Object Detection", annotated_frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("p"):
                    paused = True
                    print("Application PAUSED. Display frozen.")

    except Exception as err:
        print(f"\nCRITICAL RUNTIME ERROR: {err}")
    finally:
        # Ensure all hardware and OS resources are safely freed
        print("\nCleaning up resources...")
        cap.release()
        if writer is not None:
            writer.release()
            print(f"Saved output video file to: {args.save}")
        if not args.no_display:
            cv2.destroyAllWindows()
        print("Cleanup completed. Exiting.")


if __name__ == "__main__":
    main()
