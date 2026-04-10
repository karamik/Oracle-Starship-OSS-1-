#!/usr/bin/env python3
"""
OSS-1 Main Analyzer
Orchestrates vision and acoustic analysis to produce final report.
"""

import os
import sys
import argparse
import json
from typing import List, Dict, Any, Optional

# Import local modules
from vision_analyzer import VisionAnalyzer
from acoustic_analyzer import AcousticAnalyzer
from digital_twin import DigitalTwin
from utils import ensure_dir, list_wav_files, list_image_files, save_json, generate_html_report, Logger


# -------------------- Main Analyzer Class --------------------
class OSS1Analyzer:
    def __init__(self, baseline_dir: Optional[str] = None, defect_dir: Optional[str] = None):
        self.baseline_dir = baseline_dir
        self.defect_dir = defect_dir
        self.vision = VisionAnalyzer()
        self.acoustic = AcousticAnalyzer()
        self.digital_twin = DigitalTwin()
        self.logger = Logger("oss1_analyzer.log")
        self.results = []
    
    def load_baseline(self) -> bool:
        """Load baseline acoustic features from baseline session directory"""
        if not self.baseline_dir or not os.path.isdir(self.baseline_dir):
            self.logger.error(f"Baseline directory not found: {self.baseline_dir}")
            return False
        success = self.acoustic.load_baseline(self.baseline_dir)
        if success:
            self.logger.info(f"Loaded baseline from {self.baseline_dir}")
        else:
            self.logger.error("Failed to load baseline recordings")
        return success
    
    def analyze_tile(self, tile_id: int, image_path: Optional[str], audio_path: Optional[str]) -> Dict[str, Any]:
        """Run both vision and acoustic analysis on a single tile"""
        result = {
            "tile_id": tile_id,
            "defect_detected": False,
            "defect_type": "healthy",
            "confidence": 0.0,
            "vision": {},
            "acoustic": {},
            "combined_metrics": {}
        }
        
        # Vision analysis
        if image_path and os.path.exists(image_path):
            vision_res = self.vision.analyze_tile_image(image_path)
            result["vision"] = vision_res
            result["defect_detected"] = result["defect_detected"] or vision_res.get("defect_detected", False)
            if vision_res.get("defect_detected"):
                result["defect_type"] = vision_res.get("defect_type", "surface_defect")
                result["confidence"] = max(result["confidence"], vision_res.get("confidence", 0))
        
        # Acoustic analysis (requires baseline)
        if audio_path and os.path.exists(audio_path) and self.acoustic.baseline_features:
            acoustic_res = self.acoustic.analyze_tile(audio_path, tile_id)
            result["acoustic"] = acoustic_res
            if acoustic_res.get("defect_detected", False):
                result["defect_detected"] = True
                # If no visual defect, mark as "loose_bonding"
                if result["defect_type"] == "healthy":
                    result["defect_type"] = "loose_bonding"
                result["confidence"] = max(result["confidence"], acoustic_res.get("confidence", 0))
        
        # Combine metrics for digital twin
        combined = {
            "surface_crack_density": result["vision"].get("metrics", {}).get("crack_density", 0),
            "chip_count": result["vision"].get("metrics", {}).get("chip_count", 0),
            "oxidation_ratio": result["vision"].get("metrics", {}).get("oxidation_ratio", 0),
            "acoustic_distance": result["acoustic"].get("distance", 1.0),
        }
        result["combined_metrics"] = combined
        
        # Update digital twin
        self.digital_twin.add_record(tile_id, {
            "surface_crack_density": combined["surface_crack_density"],
            "chip_count": combined["chip_count"],
            "oxidation_ratio": combined["oxidation_ratio"],
            "acoustic_distance": combined["acoustic_distance"],
            "defect_detected": result["defect_detected"],
            "defect_type": result["defect_type"]
        })
        
        return result
    
    def run(self) -> List[Dict]:
        """Run full analysis on all tiles in defect directory, matching with baseline"""
        if not self.defect_dir or not os.path.isdir(self.defect_dir):
            self.logger.error(f"Defect directory not found: {self.defect_dir}")
            return []
        
        # Get all audio files (defect recordings)
        audio_files = list_wav_files(self.defect_dir)
        if not audio_files:
            self.logger.warn("No audio files found in defect directory")
        
        # For simplicity, assume image files are named similarly (tile_XXX.jpg/png)
        # We'll try to match by tile_id extracted from filename
        self.results = []
        for audio_file in audio_files:
            # Extract tile_id from filename (tile_XXX.wav)
            parts = audio_file.replace(".wav", "").split("_")
            if len(parts) < 2 or parts[0] != "tile":
                self.logger.warn(f"Skipping unexpected file: {audio_file}")
                continue
            tile_id = int(parts[1])
            audio_path = os.path.join(self.defect_dir, audio_file)
            # Look for corresponding image (tile_XXX.jpg or .png)
            image_path = None
            for ext in [".jpg", ".jpeg", ".png"]:
                candidate = os.path.join(self.defect_dir, f"tile_{tile_id:03d}{ext}")
                if os.path.exists(candidate):
                    image_path = candidate
                    break
            result = self.analyze_tile(tile_id, image_path, audio_path)
            self.results.append(result)
            self.logger.info(f"Analyzed tile {tile_id}: defect={result['defect_detected']} type={result['defect_type']}")
        
        # Save results
        save_json(self.results, "analysis_results.json")
        generate_html_report(self.results, "report.html")
        self.logger.info(f"Analysis complete. Report saved to report.html")
        return self.results


# -------------------- Command Line Interface --------------------
def main():
    parser = argparse.ArgumentParser(description="OSS-1 Main Analyzer")
    parser.add_argument("--baseline", required=True, help="Baseline recordings directory (e.g., recordings/baseline)")
    parser.add_argument("--defect", required=True, help="Defect recordings directory (e.g., recordings/defect)")
    parser.add_argument("--output", default="report.html", help="Output HTML report path")
    args = parser.parse_args()
    
    analyzer = OSS1Analyzer(baseline_dir=args.baseline, defect_dir=args.defect)
    if not analyzer.load_baseline():
        print("Failed to load baseline. Exiting.")
        sys.exit(1)
    results = analyzer.run()
    print(f"Analysis finished. Found {sum(1 for r in results if r['defect_detected'])} defects out of {len(results)} tiles.")
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
