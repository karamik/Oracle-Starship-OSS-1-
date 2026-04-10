#!/usr/bin/env python3
"""
OSS-1 Utilities
Helper functions for audio/image processing, logging, and file management.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


# -------------------- File Utilities --------------------
def ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist"""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def get_file_hash(filepath: str, algorithm: str = "md5") -> str:
    """Compute hash of a file for integrity checks"""
    hash_func = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def list_wav_files(directory: str) -> List[str]:
    """Return sorted list of .wav files in directory"""
    if not os.path.isdir(directory):
        return []
    files = [f for f in os.listdir(directory) if f.endswith(".wav")]
    return sorted(files)


def list_image_files(directory: str) -> List[str]:
    """Return sorted list of image files in directory"""
    if not os.path.isdir(directory):
        return []
    extensions = (".jpg", ".jpeg", ".png", ".bmp", ".tiff")
    files = [f for f in os.listdir(directory) if f.lower().endswith(extensions)]
    return sorted(files)


# -------------------- Audio Utilities --------------------
def normalize_audio(signal: np.ndarray, target_dBFS: float = -20.0) -> np.ndarray:
    """Normalize audio to target loudness (peak normalization)"""
    if np.max(np.abs(signal)) == 0:
        return signal
    peak = np.max(np.abs(signal))
    gain = 10 ** ((target_dBFS - 20 * np.log10(peak)) / 20)
    return signal * gain


def trim_silence(signal: np.ndarray, sr: int, threshold_db: float = -40, 
                 margin_sec: float = 0.1) -> np.ndarray:
    """Trim leading/trailing silence from audio"""
    # Convert to energy
    frame_length = int(0.025 * sr)
    hop_length = int(0.010 * sr)
    energy = np.array([
        np.sum(signal[i:i+frame_length]**2)
        for i in range(0, len(signal) - frame_length, hop_length)
    ])
    energy_db = 10 * np.log10(energy + 1e-10)
    above_thresh = energy_db > threshold_db
    if not np.any(above_thresh):
        return signal
    start_idx = np.argmax(above_thresh) * hop_length
    end_idx = (len(above_thresh) - np.argmax(above_thresh[::-1])) * hop_length
    # Add margin
    start_idx = max(0, start_idx - int(margin_sec * sr))
    end_idx = min(len(signal), end_idx + int(margin_sec * sr))
    return signal[start_idx:end_idx]


# -------------------- JSON & Logging --------------------
def save_json(data: Any, filepath: str, indent: int = 2) -> None:
    """Save data to JSON file"""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def load_json(filepath: str) -> Any:
    """Load data from JSON file"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        return json.load(f)


class Logger:
    """Simple logger with timestamps and levels"""
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
    
    def _log(self, level: str, msg: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}"
        print(line)
        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(line + "\n")
    
    def info(self, msg: str): self._log("INFO", msg)
    def warn(self, msg: str): self._log("WARN", msg)
    def error(self, msg: str): self._log("ERROR", msg)
    def debug(self, msg: str): self._log("DEBUG", msg)


# -------------------- Metrics Aggregation --------------------
def compute_aggregate_metrics(results: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate analysis results from multiple tiles.
    Returns summary statistics.
    """
    if not results:
        return {"total_tiles": 0, "defects_found": 0}
    
    total = len(results)
    defects = sum(1 for r in results if r.get("defect_detected", False))
    confidence_avg = np.mean([r.get("confidence", 0) for r in results])
    
    return {
        "total_tiles": total,
        "defects_found": defects,
        "defect_rate": defects / total if total > 0 else 0,
        "average_confidence": round(confidence_avg, 3)
    }


# -------------------- HTML Report Generation --------------------
def generate_html_report(results: List[Dict], output_path: str = "report.html") -> None:
    """Generate a simple HTML report from analysis results"""
    agg = compute_aggregate_metrics(results)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>OSS-1 Inspection Report</title>
    <style>
        body {{ font-family: monospace; margin: 40px; background: #0a0a0a; color: #0f0; }}
        h1 {{ color: #0f0; border-bottom: 1px solid #0f0; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #0f0; padding: 8px; text-align: left; }}
        th {{ background: #1a1a1a; }}
        .defect {{ background: #3a1a1a; color: #f99; }}
        .healthy {{ background: #1a3a1a; }}
    </style>
</head>
<body>
    <h1>OSS-1 Acoustic-Visual Inspection Report</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    <h2>Summary</h2>
    <ul>
        <li>Total tiles inspected: {agg["total_tiles"]}</li>
        <li>Defects found: {agg["defects_found"]}</li>
        <li>Defect rate: {agg["defect_rate"]:.1%}</li>
        <li>Average confidence: {agg["average_confidence"]:.2f}</li>
    </ul>
    <h2>Tile Details</h2>
    <table>
        <tr><th>Tile ID</th><th>Defect Detected</th><th>Defect Type</th><th>Confidence</th><th>Details</th></tr>
"""
    for r in results:
        defect_class = "defect" if r.get("defect_detected") else "healthy"
        html += f"""
        <tr class="{defect_class}">
            <td>{r.get("tile_id", "?")}</td>
            <td>{r.get("defect_detected", False)}</td>
            <td>{r.get("defect_type", "none")}</td>
            <td>{r.get("confidence", 0):.2f}</td>
            <td><pre>{json.dumps(r.get("metrics", {}), indent=2)[:200]}</pre></td>
        </tr>"""
    
    html += """
    </table>
</body>
</html>"""
    
    with open(output_path, "w") as f:
        f.write(html)
