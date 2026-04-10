#!/usr/bin/env python3
"""
OSS-1 Acoustic Analyzer
Detects loose tiles and bonding defects via resonance analysis of tapping sounds.
"""

import numpy as np
import librosa
import scipy.signal as signal
from scipy.spatial.distance import cosine
import os
from typing import List, Dict, Tuple, Optional
import json
import warnings
warnings.filterwarnings("ignore")

# -------------------- Configuration --------------------
class Config:
    SAMPLE_RATE = 44100
    N_FFT = 2048
    HOP_LENGTH = 512
    MEL_BANDS = 128
    MFCC_COEFFS = 20
    # Distance threshold for flagging a tile as defective (relative to baseline)
    DISTANCE_THRESHOLD = 0.35
    # Minimum frequency for resonance analysis (Hz)
    MIN_FREQ = 100
    MAX_FREQ = 5000


# -------------------- Feature Extraction --------------------
def load_audio(file_path: str) -> Tuple[Optional[np.ndarray], int]:
    """Load audio file and return signal and sample rate"""
    if not os.path.exists(file_path):
        return None, 0
    try:
        signal, sr = librosa.load(file_path, sr=Config.SAMPLE_RATE)
        return signal, sr
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None, 0


def extract_spectral_features(y: np.ndarray, sr: int) -> Dict[str, np.ndarray]:
    """Extract spectral features for resonance analysis"""
    # Mel spectrogram
    mel_spec = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=Config.N_FFT,
                                              hop_length=Config.HOP_LENGTH,
                                              n_mels=Config.MEL_BANDS)
    mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
    
    # MFCCs
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=Config.MFCC_COEFFS,
                                n_fft=Config.N_FFT, hop_length=Config.HOP_LENGTH)
    
    # Spectral centroid (resonance peak)
    cent = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=Config.N_FFT,
                                             hop_length=Config.HOP_LENGTH)
    
    # Spectral bandwidth (spread of resonance)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=Config.N_FFT,
                                                   hop_length=Config.HOP_LENGTH)
    
    # Zero-crossing rate (indicator of loose rattling)
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=Config.N_FFT,
                                             hop_length=Config.HOP_LENGTH)
    
    # Fundamental frequency (pitch of resonance)
    f0, voiced_flag, _ = librosa.pyin(y, fmin=Config.MIN_FREQ, fmax=Config.MAX_FREQ,
                                      sr=sr, hop_length=Config.HOP_LENGTH)
    f0 = np.nan_to_num(f0)
    
    return {
        "mel_spectrogram": mel_spec_db,
        "mfcc": mfcc,
        "spectral_centroid": cent.flatten(),
        "spectral_bandwidth": bandwidth.flatten(),
        "zero_crossing_rate": zcr.flatten(),
        "f0": f0
    }


def aggregate_features(features: Dict[str, np.ndarray]) -> np.ndarray:
    """Aggregate feature maps into a fixed-size vector for comparison"""
    agg = []
    # Mean and std of MFCCs (over time)
    mfcc = features["mfcc"]
    agg.extend(np.mean(mfcc, axis=1))
    agg.extend(np.std(mfcc, axis=1))
    
    # Mean spectral centroid and bandwidth
    agg.append(np.mean(features["spectral_centroid"]))
    agg.append(np.std(features["spectral_centroid"]))
    agg.append(np.mean(features["spectral_bandwidth"]))
    agg.append(np.std(features["spectral_bandwidth"]))
    
    # Mean zero-crossing rate
    agg.append(np.mean(features["zero_crossing_rate"]))
    agg.append(np.std(features["zero_crossing_rate"]))
    
    # Mean and std of fundamental frequency
    f0 = features["f0"]
    f0_nonzero = f0[f0 > 0]
    if len(f0_nonzero) > 0:
        agg.append(np.mean(f0_nonzero))
        agg.append(np.std(f0_nonzero))
    else:
        agg.append(0)
        agg.append(0)
    
    return np.array(agg)


# -------------------- Baseline and Comparison --------------------
class AcousticAnalyzer:
    def __init__(self):
        self.baseline_features: Dict[int, np.ndarray] = {}  # tile_id -> aggregated vector
    
    def load_baseline(self, session_dir: str) -> bool:
        """Load all baseline recordings from a session directory"""
        if not os.path.isdir(session_dir):
            return False
        
        self.baseline_features = {}
        for fname in sorted(os.listdir(session_dir)):
            if fname.endswith(".wav"):
                # Extract tile ID from filename (tile_XXX.wav)
                parts = fname.replace(".wav", "").split("_")
                if len(parts) >= 2 and parts[0] == "tile":
                    tile_id = int(parts[1])
                    filepath = os.path.join(session_dir, fname)
                    y, sr = load_audio(filepath)
                    if y is not None:
                        features = extract_spectral_features(y, sr)
                        agg = aggregate_features(features)
                        self.baseline_features[tile_id] = agg
        return len(self.baseline_features) > 0
    
    def analyze_tile(self, defect_audio_path: str, tile_id: int) -> Dict[str, any]:
        """
        Compare a defect recording against baseline for the same tile_id.
        Returns dict with distance and defect flag.
        """
        if tile_id not in self.baseline_features:
            return {
                "defect_detected": False,
                "distance": 1.0,
                "confidence": 0.0,
                "error": f"No baseline for tile {tile_id}"
            }
        
        y, sr = load_audio(defect_audio_path)
        if y is None:
            return {
                "defect_detected": False,
                "distance": 1.0,
                "confidence": 0.0,
                "error": "Audio loading failed"
            }
        
        features = extract_spectral_features(y, sr)
        agg = aggregate_features(features)
        baseline = self.baseline_features[tile_id]
        
        # Compute cosine distance (0 = identical, 1 = orthogonal, >1 = opposite)
        distance = cosine(baseline, agg)
        defect_detected = distance > Config.DISTANCE_THRESHOLD
        confidence = min(1.0, distance / Config.DISTANCE_THRESHOLD) if defect_detected else 1.0 - distance
        
        return {
            "defect_detected": defect_detected,
            "distance": distance,
            "confidence": confidence,
            "tile_id": tile_id
        }
    
    def analyze_panel(self, defect_session_dir: str) -> List[Dict]:
        """
        Compare all defect recordings against baseline (baseline must be pre-loaded).
        Assumes filenames match baseline naming.
        """
        results = []
        for fname in sorted(os.listdir(defect_session_dir)):
            if fname.endswith(".wav"):
                parts = fname.replace(".wav", "").split("_")
                if len(parts) >= 2 and parts[0] == "tile":
                    tile_id = int(parts[1])
                    filepath = os.path.join(defect_session_dir, fname)
                    res = self.analyze_tile(filepath, tile_id)
                    res["file"] = fname
                    results.append(res)
        return results


# -------------------- Command-line entry point --------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python acoustic_analyzer.py <baseline_dir> <defect_dir>")
        sys.exit(1)
    
    baseline_dir = sys.argv[1]
    defect_dir = sys.argv[2]
    
    analyzer = AcousticAnalyzer()
    if not analyzer.load_baseline(baseline_dir):
        print("Failed to load baseline recordings.")
        sys.exit(1)
    
    results = analyzer.analyze_panel(defect_dir)
    print(json.dumps(results, indent=2))
