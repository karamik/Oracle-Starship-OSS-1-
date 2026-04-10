#!/usr/bin/env python3
"""
OSS-1 Vision Analyzer
Detects surface defects on TPS tiles using computer vision and neural networks.
"""

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
import os
from typing import List, Dict, Tuple, Optional
import json
import warnings
warnings.filterwarnings("ignore")

# -------------------- Configuration --------------------
class Config:
    IMG_SIZE = (224, 224)  # Input size for neural network
    MODEL_PATH = "models/surface_crack.pt"
    CONFIDENCE_THRESHOLD = 0.6  # Minimum confidence to flag a defect
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# -------------------- Neural Network Model --------------------
class DefectDetectorNet(nn.Module):
    """Simple CNN for defect classification (surface cracks, chipping, oxidation)"""
    def __init__(self, num_classes=4):  # classes: crack, chip, oxidation, healthy
        super(DefectDetectorNet, self).__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(128, 256, 3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1)
        )
        self.classifier = nn.Linear(256, num_classes)
    
    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        x = self.classifier(x)
        return x


# -------------------- Image Preprocessing --------------------
def load_image(image_path: str) -> Optional[np.ndarray]:
    """Load and preprocess image for analysis"""
    if not os.path.exists(image_path):
        return None
    img = cv2.imread(image_path)
    if img is None:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def preprocess_for_model(img: np.ndarray) -> torch.Tensor:
    """Resize, normalize, and convert to tensor"""
    img_resized = cv2.resize(img, Config.IMG_SIZE)
    img_tensor = torch.from_numpy(img_resized).float().permute(2, 0, 1) / 255.0
    img_tensor = img_tensor.unsqueeze(0)  # add batch dimension
    return img_tensor


# -------------------- Feature Extraction (Traditional CV) --------------------
def detect_cracks_sobel(img: np.ndarray) -> float:
    """Use Sobel edge detection to estimate crack density"""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.sqrt(sobelx**2 + sobely**2)
    # Normalize and threshold
    magnitude = magnitude / magnitude.max()
    crack_density = np.mean(magnitude > 0.3)
    return float(crack_density)


def detect_chips_contours(img: np.ndarray) -> int:
    """Detect missing or chipped areas using contour analysis"""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Count significant defects (area > 10 pixels)
    chip_count = sum(1 for c in contours if cv2.contourArea(c) > 10)
    return chip_count


def detect_oxidation_color(img: np.ndarray) -> float:
    """Estimate oxidation by analyzing color deviation"""
    # Convert to HSV and look for brownish/discolored areas
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    # Normal tile color range (adjustable)
    lower_normal = np.array([0, 0, 200])
    upper_normal = np.array([180, 50, 255])
    mask_normal = cv2.inRange(hsv, lower_normal, upper_normal)
    oxidation_ratio = 1.0 - (np.sum(mask_normal > 0) / (img.shape[0] * img.shape[1]))
    return float(oxidation_ratio)


# -------------------- Main Analyzer Class --------------------
class VisionAnalyzer:
    def __init__(self):
        self.device = Config.DEVICE
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load pre-trained neural network if available, otherwise use fallback"""
        if os.path.exists(Config.MODEL_PATH):
            try:
                self.model = DefectDetectorNet(num_classes=4)
                self.model.load_state_dict(torch.load(Config.MODEL_PATH, map_location=self.device))
                self.model.to(self.device)
                self.model.eval()
                print(f"Loaded model from {Config.MODEL_PATH}")
            except Exception as e:
                print(f"Warning: Could not load model: {e}. Using fallback methods.")
                self.model = None
        else:
            print("No pre-trained model found. Using fallback computer vision methods.")
            self.model = None
    
    def analyze_tile_image(self, image_path: str) -> Dict[str, any]:
        """
        Analyze a single tile image and return defect metrics.
        Returns dict with:
            - defect_detected: bool
            - defect_type: str (crack/chip/oxidation/healthy)
            - confidence: float
            - metrics: dict with detailed measurements
        """
        img = load_image(image_path)
        if img is None:
            return {
                "defect_detected": False,
                "defect_type": "error",
                "confidence": 0.0,
                "metrics": {"error": "Image not found"}
            }
        
        # Extract features using traditional CV (always available)
        crack_score = detect_cracks_sobel(img)
        chip_score = detect_chips_contours(img)
        oxidation_score = detect_oxidation_color(img)
        
        metrics = {
            "crack_density": crack_score,
            "chip_count": chip_score,
            "oxidation_ratio": oxidation_score,
        }
        
        # Use neural network if available
        nn_confidence = 0.0
        nn_class = "healthy"
        
        if self.model is not None:
            tensor = preprocess_for_model(img).to(self.device)
            with torch.no_grad():
                output = self.model(tensor)
                probs = torch.softmax(output, dim=1)
                confidence, class_idx = torch.max(probs, 1)
                nn_confidence = confidence.item()
                classes = ["crack", "chip", "oxidation", "healthy"]
                nn_class = classes[class_idx.item()]
        
        # Combine traditional metrics for final decision
        defect_detected = (crack_score > 0.05) or (chip_score > 2) or (oxidation_score > 0.3)
        
        # Determine defect type based on strongest signal
        if defect_detected:
            if crack_score > 0.05:
                defect_type = "crack"
            elif chip_score > 2:
                defect_type = "chip"
            else:
                defect_type = "oxidation"
        else:
            defect_type = "healthy"
        
        # Overall confidence (mix of NN and heuristic)
        confidence = max(nn_confidence, 0.5) if defect_detected else 0.9
        
        return {
            "defect_detected": defect_detected,
            "defect_type": defect_type,
            "confidence": confidence,
            "metrics": metrics,
            "nn_prediction": nn_class,
            "nn_confidence": nn_confidence
        }
    
    def analyze_panel(self, image_paths: List[str]) -> List[Dict]:
        """Analyze multiple tiles and return list of results"""
        results = []
        for idx, img_path in enumerate(image_paths):
            tile_result = self.analyze_tile_image(img_path)
            tile_result["tile_id"] = idx + 1
            tile_result["image_path"] = img_path
            results.append(tile_result)
        return results


# -------------------- Command-line entry point --------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python vision_analyzer.py <image_path> [image_path2 ...]")
        sys.exit(1)
    
    analyzer = VisionAnalyzer()
    for img_path in sys.argv[1:]:
        result = analyzer.analyze_tile_image(img_path)
        print(json.dumps(result, indent=2))
