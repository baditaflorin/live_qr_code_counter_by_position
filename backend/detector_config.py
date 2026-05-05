"""Detector configuration with runtime-tunable parameters and persistence."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Literal, Optional


class DetectorType(str, Enum):
    """Available detector implementations."""
    APRILTAG = "apriltag"
    ARUCO = "aruco"


@dataclass
class AprilTagConfig:
    """AprilTag-specific detector parameters."""
    quad_decimate: float = 4.0      # 1.0=accurate/slow, 8.0=fast/inaccurate
    quad_sigma: float = 0.0         # Edge blur (0=off, 0.5-2.0=more blur)
    refine_edges: bool = False      # CPU-intensive edge refinement
    decode_sharpening: float = 0.0  # Sharpening (0=off, 0.5-2.0=more)
    nthreads: int = 4               # Parallel threads for detection


@dataclass
class ArUcoConfig:
    """ArUco-specific detector parameters."""
    adaptiveThreshWinSizeMin: int = 5
    adaptiveThreshWinSizeMax: int = 35
    adaptiveThreshWinSizeStep: int = 6
    minMarkerPerimeterRate: float = 0.02
    cornerRefinementMethod: str = "CORNER_REFINE_SUBPIX"


@dataclass
class DetectorConfig:
    """Complete detector configuration with all tunable parameters."""
    detector_type: DetectorType = DetectorType.APRILTAG
    marker_size_m: float = 0.05
    dual_detection_mode: bool = False
    apriltag: AprilTagConfig = field(default_factory=AprilTagConfig)
    aruco: ArUcoConfig = field(default_factory=ArUcoConfig)

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization."""
        return {
            "detector_type": self.detector_type.value,
            "marker_size_m": self.marker_size_m,
            "dual_detection_mode": self.dual_detection_mode,
            "apriltag": asdict(self.apriltag),
            "aruco": asdict(self.aruco),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DetectorConfig":
        """Create config from dictionary (e.g., loaded from JSON)."""
        detector_type = DetectorType(data.get("detector_type", "apriltag"))
        marker_size_m = data.get("marker_size_m", 0.05)
        dual_detection_mode = data.get("dual_detection_mode", False)

        apriltag_data = data.get("apriltag", {})
        apriltag = AprilTagConfig(**{k: v for k, v in apriltag_data.items() if k in AprilTagConfig.__dataclass_fields__})

        aruco_data = data.get("aruco", {})
        aruco = ArUcoConfig(**{k: v for k, v in aruco_data.items() if k in ArUcoConfig.__dataclass_fields__})

        return cls(
            detector_type=detector_type,
            marker_size_m=marker_size_m,
            dual_detection_mode=dual_detection_mode,
            apriltag=apriltag,
            aruco=aruco,
        )

    @staticmethod
    def load_from_env() -> DetectorConfig:
        """Load configuration from environment variables."""
        detector_type = DetectorType(os.environ.get("DETECTOR_TYPE", "apriltag"))
        marker_size_m = float(os.environ.get("MARKER_SIZE_M", "0.05"))
        dual_detection_mode = os.environ.get("DUAL_DETECTION_MODE", "false").lower() == "true"

        apriltag = AprilTagConfig(
            quad_decimate=float(os.environ.get("APRILTAG_QUAD_DECIMATE", "4.0")),
            quad_sigma=float(os.environ.get("APRILTAG_QUAD_SIGMA", "0.0")),
            refine_edges=os.environ.get("APRILTAG_REFINE_EDGES", "false").lower() == "true",
            decode_sharpening=float(os.environ.get("APRILTAG_DECODE_SHARPENING", "0.0")),
            nthreads=int(os.environ.get("APRILTAG_NTHREADS", "4")),
        )

        aruco = ArUcoConfig(
            adaptiveThreshWinSizeMin=int(os.environ.get("ARUCO_WIN_SIZE_MIN", "5")),
            adaptiveThreshWinSizeMax=int(os.environ.get("ARUCO_WIN_SIZE_MAX", "35")),
            adaptiveThreshWinSizeStep=int(os.environ.get("ARUCO_WIN_SIZE_STEP", "6")),
            minMarkerPerimeterRate=float(os.environ.get("ARUCO_MIN_PERIMETER", "0.02")),
            cornerRefinementMethod=os.environ.get("ARUCO_CORNER_REFINE", "CORNER_REFINE_SUBPIX"),
        )

        return DetectorConfig(
            detector_type=detector_type,
            marker_size_m=marker_size_m,
            dual_detection_mode=dual_detection_mode,
            apriltag=apriltag,
            aruco=aruco,
        )

    @staticmethod
    def load_from_disk(data_dir: str) -> Optional["DetectorConfig"]:
        """Load configuration from JSON file. Returns None if file doesn't exist."""
        config_path = Path(data_dir) / "detector_config.json"
        if not config_path.exists():
            return None
        try:
            with open(config_path) as f:
                data = json.load(f)
            return DetectorConfig.from_dict(data)
        except Exception as e:
            print(f"Warning: Failed to load detector config from {config_path}: {e}")
            return None

    def save_to_disk(self, data_dir: str) -> None:
        """Persist configuration to JSON file."""
        config_path = Path(data_dir) / "detector_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save detector config to {config_path}: {e}")


class ConfigManager:
    """Thread-safe manager for detector configuration updates."""

    def __init__(self, initial_config: DetectorConfig):
        self._config = initial_config
        self._lock = threading.RLock()

    def get_config(self) -> DetectorConfig:
        """Get current configuration (thread-safe)."""
        with self._lock:
            # Return a copy to prevent external mutations
            return DetectorConfig(
                detector_type=self._config.detector_type,
                marker_size_m=self._config.marker_size_m,
                dual_detection_mode=self._config.dual_detection_mode,
                apriltag=AprilTagConfig(**asdict(self._config.apriltag)),
                aruco=ArUcoConfig(**asdict(self._config.aruco)),
            )

    def set_config(self, config: DetectorConfig) -> None:
        """Update configuration (thread-safe)."""
        with self._lock:
            self._config = config

    def update_config(self, updates: dict) -> DetectorConfig:
        """Update only specific fields and return the new config."""
        with self._lock:
            current = self.get_config()
            # Merge updates into current config
            config_dict = current.to_dict()
            config_dict.update(updates)
            new_config = DetectorConfig.from_dict(config_dict)
            self._config = new_config
            return new_config
