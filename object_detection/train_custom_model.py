"""
Training Script Template for YOLOv8 Custom Models
===================================================
Use this script to train the model to recognize custom objects (like hands, fingers, etc.)
that are not included in the standard pre-trained COCO dataset.

Steps:
1. Install requirements:
   pip install ultralytics opencv-python

2. Prepare custom dataset in YOLO format:
   Create a folder structure in your workspace:
   dataset/
     ├── images/
     │     ├── train/  (training images)
     │     └── val/    (validation images)
     └── labels/
           ├── train/  (YOLO format text files with bounding boxes)
           └── val/    (YOLO format text files with bounding boxes)

   YOLO label format (one text file per image, space-separated float coordinates):
   <class_id> <x_center> <y_center> <width> <height>
   Example:
   0 0.45 0.52 0.12 0.08  (represents a hand labeled as class 0)

3. Create a config file named `dataset.yaml`:
   -------------------------------------------------
   path: ./dataset  # root directory of dataset
   train: images/train
   val: images/val

   # Class Names dictionary
   names:
     0: hand
     1: finger
   -------------------------------------------------

4. Run this script to start training.
"""

import sys
import os

try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics library is not installed. Please install it by running:")
    print("pip install ultralytics")
    sys.exit(1)

def run_training():
    # 1. Config file check
    config_path = "dataset.yaml"
    if not os.path.exists(config_path):
        print(f"Warning: '{config_path}' was not found in the current directory.")
        print("Please create a 'dataset.yaml' file describing your dataset path and labels.")
        print("Using sample dataset configuration...")
        
        # Write a sample dataset.yaml for convenience
        with open("sample_dataset.yaml", "w") as f:
            f.write(
                "# Sample Dataset Configuration\n"
                "path: ./custom_data\n"
                "train: images/train\n"
                "val: images/val\n"
                "\n"
                "names:\n"
                "  0: hand\n"
                "  1: finger\n"
            )
        print("Created template 'sample_dataset.yaml'. Edit it and rename to 'dataset.yaml'.")
        return

    # 2. Load the base model.
    # We use the medium model (yolov8m.pt) as it is highly accurate while remaining efficient on CPUs.
    print("Loading pre-trained base model: yolov8m.pt...")
    model = YOLO("yolov8m.pt")

    # 3. Run training
    print("Starting custom model training...")
    try:
        # epochs: Number of passes over the dataset. 50-100 is a good starting point.
        # imgsz: Image size (640 is standard).
        # batch: Batch size (adjust based on RAM/VRAM, e.g., 8, 16, 32).
        # device: Set to '0' to use CUDA GPU if available, or 'cpu'.
        results = model.train(
            data=config_path,
            epochs=50,
            imgsz=640,
            batch=16,
            device="cpu", # Change to 0 for Nvidia GPU training
            workers=4,
            project="custom_vision",
            name="analyzer_model"
        )
        print("\nTraining completed successfully!")
        print("Your custom trained weights are saved in: custom_vision/analyzer_model/weights/best.pt")
        print("To use your new model, copy 'best.pt' to the root directory and update config.py to load it.")
    except Exception as e:
        print(f"An error occurred during training: {e}")

if __name__ == "__main__":
    run_training()
