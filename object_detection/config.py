"""Configuration module for the real-time object detection application."""

import cv2

DEFAULT_MODEL: str = "yolo11n.pt"   # YOLOv11 nano model — fastest CPU inference with good accuracy
WORLD_MODEL:   str = "yolov8s-worldv2.pt"  # open-vocabulary world model
USE_WORLD_MODEL: bool = False        # YOLOWorld needs CLIP dep — using yolov8m (80 classes)

DEFAULT_CONF: float = 0.20           # Lower threshold to detect more objects; class-specific overrides filter false positives
DEFAULT_DEVICE: str = "cpu"
FILTERED_CLASSES: list[int] = [0, 67]  # Restrict to human/person (0) and cell phone (67)

# Class-specific confidence overrides to filter out spurious detections
# Animals are prone to false-positives on human limbs/clothes, hence higher thresholds.
CLASS_CONF_THRESHOLDS: dict[str, float] = {
    "person": 0.25,
    "cat": 0.85,     # Very high to block false-positive cat on person
    "dog": 0.80,     # Very high to block false-positive dog on person
    "bird": 0.65,
}

# Priority score to resolve overlap conflicts during deduplication
# Highly reliable or critical classes (like person) get higher priority.
CLASS_PRIORITIES: dict[str, int] = {
    "person": 10,
    "cell phone": 5,
    # defaults to 1 for standard objects
}



# ── Comprehensive class list for YOLOWorld ────────────────────────────────────
# Includes everything the user might want to detect — far beyond COCO 80 classes
WORLD_CLASSES: list[str] = [
    # People & body parts
    "person", "face", "hand", "finger", "arm", "leg", "foot",
    # Vehicles
    "car", "motorcycle", "bicycle", "bus", "truck", "van", "scooter",
    "airplane", "boat", "train", "ambulance", "fire truck",
    # Animals
    "cat", "dog", "bird", "horse", "cow", "elephant", "bear", "zebra",
    "giraffe", "sheep", "fish",
    # Electronics & devices
    "laptop", "computer", "monitor", "keyboard", "mouse", "phone",
    "cell phone", "tablet", "camera", "headphones", "tv", "remote",
    "printer", "charger", "speaker",
    # Writing & office
    "pen", "pencil", "marker", "book", "notebook", "paper",
    "scissors", "ruler", "stapler", "folder",
    # Food & drink
    "cup", "bottle", "glass", "mug", "bowl", "plate", "fork", "knife",
    "spoon", "apple", "banana", "orange", "pizza", "sandwich", "cake",
    "donut", "bread", "burger",
    # Furniture & indoor
    "chair", "table", "desk", "sofa", "couch", "bed", "lamp",
    "shelf", "cabinet", "door", "window", "bag", "backpack",
    "suitcase", "umbrella", "wallet", "watch",
    # Outdoor & street
    "traffic light", "stop sign", "fire hydrant", "bench", "clock",
    "vase", "plant", "tree", "flower",
    # Sports
    "ball", "sports ball", "tennis racket", "skateboard", "surfboard",
    "baseball bat",
    # Clothing
    "shoe", "hat", "glasses", "sunglasses",
]

# ── OpenCV drawing settings ───────────────────────────────────────────────────
FONT: int = cv2.FONT_HERSHEY_DUPLEX
FONT_SCALE: float = 0.60
FONT_THICKNESS: int = 1
BOX_THICKNESS: int = 2  # Bold solid box borders

TEXT_COLOR: tuple[int, int, int] = (255, 255, 255)

# Vivid, high-contrast neon class colors (BGR)
CLASS_COLORS: list[tuple[int, int, int]] = [
    (255, 128,   0),   # Electric Cyan/Blue
    (  0, 255, 127),   # Neon Green
    (255, 255,   0),   # Neon Yellow-Green
    (255,   0, 255),   # Hot Magenta
    (  0, 180, 255),   # Bright Orange
    (  0, 255, 255),   # Pure Neon Yellow
    (255,   0, 127),   # Neon Pink
    (127,   0, 255),   # Bright Violet
    (  0, 255, 180),   # Neon Mint
    (255, 100,   0),   # Bright Cyan
    (180, 255,   0),   # Bright Lime
    (255,   0, 180),   # Neon Rose
    (  0, 100, 255),   # Vivid Orange-Red
    (255, 180,   0),   # Sky Blue
    (  0, 200, 120),   # Soft Neon Green
    (150,   0, 255),   # Purple-Blue
]

# Named per-class color overrides (BGR) — always consistent color for key classes
NAMED_CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "person":        (  0, 140, 255),   # Bright Orange
    "car":           (255, 200,   0),   # Cyan
    "bicycle":       (  0, 255, 127),   # Neon Green
    "motorcycle":    (255,   0, 255),   # Hot Magenta
    "bus":           (  0, 255, 255),   # Yellow
    "truck":         (255, 100,   0),   # Deep Cyan
    "cat":           (255,   0, 127),   # Neon Pink
    "dog":           (127,   0, 255),   # Violet
    "bird":          (  0, 255, 180),   # Mint
    "cell phone":    (180, 255,   0),   # Lime
    "laptop":        (255, 180,   0),   # Sky Blue
    "bottle":        (  0, 200, 120),   # Soft Green
    "chair":         (150,   0, 255),   # Purple
    "tv":            (255, 255,   0),   # Bright Yellow-Green
    "book":          (  0, 100, 255),   # Vivid Orange-Red
    "backpack":      (255, 128,   0),   # Electric Cyan/Blue
}

# Overlay settings

OVERLAY_BG_COLOR: tuple[int, int, int] = (15, 15, 15)
OVERLAY_ALPHA: float = 0.75

# Standard COCO 80 classes (fallback when not using World model)
COCO_CLASSES: list[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
]
