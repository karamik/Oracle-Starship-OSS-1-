#!/usr/bin/env python3
"""
OSS-1 Digital Twin
Tracks per-tile health scores across multiple flights and predicts future failures.
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np


# -------------------- Configuration --------------------
class Config:
    HEALTH_DB_PATH = "digital_twin_db.json"
    # Health score weights (0-1, sum to 1)
    WEIGHTS = {
        "surface_cracks": 0.3,
        "chip_damage": 0.25,
        "oxidation": 0.2,
        "acoustic_distance": 0.25
    }
    # Thresholds for flagging tile for replacement
    REPLACE_THRESHOLD = 0.7  # Health score below 0.7 triggers replacement
    WARNING_THRESHOLD = 0.85  # Below 0.85 triggers warning/inspection


# -------------------- Health Score Calculation --------------------
def compute_health_score(surface_score: float, chip_count: int, 
                         oxidation_ratio: float, acoustic_distance: float) -> float:
    """
    Compute overall health score from individual metrics.
    Returns value between 0 (failed) and 1 (perfect).
    """
    # Normalize chip count (0-10 chips => 1-0)
    chip_norm = max(0, min(1, 1 - chip_count / 10))
    # Normalize oxidation ratio (0-1 => 1-0)
    oxidation_norm = 1 - min(1, oxidation_ratio)
    # Acoustic distance normalized: 0 -> 1, >0.5 -> 0
    acoustic_norm = max(0, 1 - acoustic_distance / 0.5)
    # Surface crack density: 0 -> 1, >0.2 -> 0
    surface_norm = max(0, 1 - surface_score / 0.2)
    
    weighted_sum = (surface_norm * Config.WEIGHTS["surface_cracks"] +
                    chip_norm * Config.WEIGHTS["chip_damage"] +
                    oxidation_norm * Config.WEIGHTS["oxidation"] +
                    acoustic_norm * Config.WEIGHTS["acoustic_distance"])
    
    return round(weighted_sum, 3)


# -------------------- Digital Twin Database --------------------
class DigitalTwin:
    def __init__(self, db_path: str = Config.HEALTH_DB_PATH):
        self.db_path = db_path
        self.data: Dict[int, List[Dict]] = {}  # tile_id -> list of inspection records
        self._load()
    
    def _load(self):
        """Load database from JSON file"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    self.data = {int(k): v for k, v in json.load(f).items()}
            except Exception:
                self.data = {}
    
    def _save(self):
        """Save database to JSON file"""
        with open(self.db_path, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def add_record(self, tile_id: int, inspection_data: Dict[str, Any]):
        """
        Add an inspection record for a tile.
        inspection_data should contain:
            - timestamp (str, optional)
            - surface_crack_density (float)
            - chip_count (int)
            - oxidation_ratio (float)
            - acoustic_distance (float)
            - defect_detected (bool)
            - defect_type (str, optional)
        """
        record = inspection_data.copy()
        if "timestamp" not in record:
            record["timestamp"] = datetime.now().isoformat()
        
        # Compute health score if metrics present
        if all(k in record for k in ["surface_crack_density", "chip_count", 
                                     "oxidation_ratio", "acoustic_distance"]):
            record["health_score"] = compute_health_score(
                record["surface_crack_density"],
                record["chip_count"],
                record["oxidation_ratio"],
                record["acoustic_distance"]
            )
        else:
            record["health_score"] = None
        
        if tile_id not in self.data:
            self.data[tile_id] = []
        self.data[tile_id].append(record)
        self._save()
    
    def get_tile_history(self, tile_id: int) -> List[Dict]:
        """Return all inspection records for a tile"""
        return self.data.get(tile_id, [])
    
    def get_current_health(self, tile_id: int) -> Optional[float]:
        """Return most recent health score for a tile"""
        history = self.get_tile_history(tile_id)
        if not history:
            return None
        latest = history[-1]
        return latest.get("health_score")
    
    def predict_failure_risk(self, tile_id: int) -> Dict[str, Any]:
        """
        Predict risk of failure in next flight based on health trend.
        Returns dict with risk_score (0-1) and recommendation.
        """
        history = self.get_tile_history(tile_id)
        if len(history) < 2:
            return {"risk_score": 0.0, "recommendation": "Insufficient data"}
        
        # Extract health scores over time
        scores = [h.get("health_score") for h in history if h.get("health_score") is not None]
        if len(scores) < 2:
            return {"risk_score": 0.0, "recommendation": "Insufficient health scores"}
        
        # Calculate trend (linear regression slope)
        x = np.arange(len(scores))
        slope = np.polyfit(x, scores, 1)[0]
        
        # Predict next health score
        next_score = scores[-1] + slope
        next_score = max(0, min(1, next_score))
        
        risk = 1 - next_score  # risk = 1 - predicted health
        
        if risk > 0.5:
            rec = "Replace immediately"
        elif risk > 0.3:
            rec = "Inspect before next flight"
        else:
            rec = "Continue monitoring"
        
        return {
            "risk_score": round(risk, 3),
            "predicted_health": round(next_score, 3),
            "trend": "degrading" if slope < -0.05 else "stable" if abs(slope) < 0.05 else "improving",
            "recommendation": rec
        }
    
    def get_panel_summary(self, tile_ids: List[int]) -> Dict[str, Any]:
        """
        Generate summary report for a panel or full ship.
        Returns dict with statistics and recommendations.
        """
        summary = {
            "total_tiles": len(tile_ids),
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "no_data": 0,
            "tile_status": {}
        }
        
        for tile_id in tile_ids:
            health = self.get_current_health(tile_id)
            if health is None:
                summary["no_data"] += 1
                status = "no_data"
            elif health >= Config.WARNING_THRESHOLD:
                summary["healthy"] += 1
                status = "healthy"
            elif health >= Config.REPLACE_THRESHOLD:
                summary["warning"] += 1
                status = "warning"
            else:
                summary["critical"] += 1
                status = "critical"
            summary["tile_status"][tile_id] = {"health": health, "status": status}
        
        return summary


# -------------------- Command-line entry point --------------------
if __name__ == "__main__":
    import sys
    twin = DigitalTwin()
    
    if len(sys.argv) < 2:
        print("Usage: python digital_twin.py <command> [args]")
        print("Commands:")
        print("  add <tile_id> <surface> <chips> <oxidation> <acoustic>")
        print("  health <tile_id>")
        print("  predict <tile_id>")
        print("  summary <tile_id1,tile_id2,...>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "add" and len(sys.argv) == 7:
        tile_id = int(sys.argv[2])
        surface = float(sys.argv[3])
        chips = int(sys.argv[4])
        oxidation = float(sys.argv[5])
        acoustic = float(sys.argv[6])
        twin.add_record(tile_id, {
            "surface_crack_density": surface,
            "chip_count": chips,
            "oxidation_ratio": oxidation,
            "acoustic_distance": acoustic
        })
        print(f"Added record for tile {tile_id}")
    
    elif cmd == "health" and len(sys.argv) == 3:
        tile_id = int(sys.argv[2])
        health = twin.get_current_health(tile_id)
        print(f"Tile {tile_id} current health: {health}")
    
    elif cmd == "predict" and len(sys.argv) == 3:
        tile_id = int(sys.argv[2])
        risk = twin.predict_failure_risk(tile_id)
        print(json.dumps(risk, indent=2))
    
    elif cmd == "summary" and len(sys.argv) == 3:
        tile_ids = [int(x) for x in sys.argv[2].split(",")]
        summary = twin.get_panel_summary(tile_ids)
        print(json.dumps(summary, indent=2))
    
    else:
        print("Invalid command or arguments.")
