"""Detector factory and implementations (AprilTag, ArUco, Dual)."""
from abc import ABC, abstractmethod
from typing import Optional
import cv2
import numpy as np
from pupil_apriltags import Detector as AprilTagDetectorLib

from . import detection as _detection_module
from .detector_config import DetectorConfig, DetectorType


class BaseDetector(ABC):
    """Abstract base class for marker detection implementations."""

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray) -> list["_detection_module.Detection"]:
        """Detect markers in a BGR frame. Returns list of Detection objects."""
        pass

    @abstractmethod
    def estimate_pose(
        self,
        detections: list["_detection_module.Detection"],
        K: np.ndarray,
        dist: np.ndarray,
        marker_size_m: float,
        *,
        filters: Optional[dict[int, "_detection_module._pose_filter.PoseFilter"]] = None,
        ts: Optional[float] = None,
    ) -> dict[int, "_detection_module.PoseDetection"]:
        """Estimate 6-DOF pose for detected markers (ADR 0048)."""
        pass

    @abstractmethod
    def get_dictionary_name(self) -> str:
        """Get the name of the marker dictionary."""
        pass

    @abstractmethod
    def dictionary_size(self) -> int:
        """Get the number of unique markers in the dictionary."""
        pass


class AprilTagDetector(BaseDetector):
    """AprilTag detector using pupil-apriltags library."""

    def __init__(self, config: DetectorConfig):
        self.config = config
        apriltag_cfg = config.apriltag
        self._detector = AprilTagDetectorLib(
            families="tag36h11",
            nthreads=apriltag_cfg.nthreads,
            quad_decimate=apriltag_cfg.quad_decimate,
            quad_sigma=apriltag_cfg.quad_sigma,
            refine_edges=apriltag_cfg.refine_edges,
            decode_sharpening=apriltag_cfg.decode_sharpening,
            debug=False,
        )

    def detect(self, frame_bgr: np.ndarray) -> list["_detection_module.Detection"]:
        """Detect AprilTags in frame using pupil-apriltags."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        detections = self._detector.detect(gray, estimate_tag_pose=False)
        out: list["_detection_module.Detection"] = []
        for detection in detections:
            tag_id = detection.tag_id
            corners_array = np.array(detection.corners, dtype=np.float32)
            center = corners_array.mean(axis=0)
            out.append(
                _detection_module.Detection(
                    tag_id=int(tag_id),
                    corners=[[float(p[0]), float(p[1])] for p in corners_array],
                    center=[float(center[0]), float(center[1])],
                    _raw_corners=corners_array,
                )
            )
        return out

    def estimate_pose(
        self,
        detections: list["_detection_module.Detection"],
        K: np.ndarray,
        dist: np.ndarray,
        marker_size_m: float,
        *,
        filters: Optional[dict[int, "_detection_module._pose_filter.PoseFilter"]] = None,
        ts: Optional[float] = None,
    ) -> dict[int, "_detection_module.PoseDetection"]:
        """Estimate pose using AprilTag-specific IPPE method."""
        # Use AprilTag-specific pose estimation (IPPE with PoseFilter smoothing)
        return _detection_module.estimate_pose_apriltag(detections, K, dist, marker_size_m, filters=filters, ts=ts)

    def get_dictionary_name(self) -> str:
        return "tag36h11"

    def dictionary_size(self) -> int:
        return 587


class ArUcoDetector(BaseDetector):
    """ArUco detector using OpenCV's cv2.aruco module."""

    def __init__(self, config: DetectorConfig):
        self.config = config
        aruco_cfg = config.aruco

        # Get the ArUco dictionary
        self._dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)

        # Create detector parameters
        self._params = cv2.aruco.DetectorParameters()
        self._params.adaptiveThreshWinSizeMin = aruco_cfg.adaptiveThreshWinSizeMin
        self._params.adaptiveThreshWinSizeMax = aruco_cfg.adaptiveThreshWinSizeMax
        self._params.adaptiveThreshWinSizeStep = aruco_cfg.adaptiveThreshWinSizeStep
        self._params.minMarkerPerimeterRate = aruco_cfg.minMarkerPerimeterRate

        # Set corner refinement method
        if aruco_cfg.cornerRefinementMethod == "CORNER_REFINE_SUBPIX":
            self._params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        else:
            self._params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE

        self._detector = cv2.aruco.ArucoDetector(self._dictionary, self._params)

    def detect(self, frame_bgr: np.ndarray) -> list["_detection_module.Detection"]:
        """Detect ArUco markers in frame."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = self._detector.detectMarkers(gray)

        out: list["_detection_module.Detection"] = []
        if ids is not None:
            for i, corner_group in enumerate(corners):
                marker_id = int(ids[i][0])
                # corner_group is shape (1, 4, 2) - reshape to (4, 2)
                corners_array = corner_group[0].astype(np.float32)
                center = corners_array.mean(axis=0)
                out.append(
                    _detection_module.Detection(
                        tag_id=marker_id,
                        corners=[[float(p[0]), float(p[1])] for p in corners_array],
                        center=[float(center[0]), float(center[1])],
                        _raw_corners=corners_array,
                    )
                )
        return out

    def estimate_pose(
        self,
        detections: list["_detection_module.Detection"],
        K: np.ndarray,
        dist: np.ndarray,
        marker_size_m: float,
        *,
        filters: Optional[dict[int, "_detection_module._pose_filter.PoseFilter"]] = None,
        ts: Optional[float] = None,
    ) -> dict[int, "_detection_module.PoseDetection"]:
        """Estimate pose for ArUco detections using solvePnP."""
        if not detections:
            return {}

        K = np.asarray(K, dtype=np.float64)
        dist = np.asarray(dist, dtype=np.float64).reshape(-1)
        obj_pts = self._marker_object_points(marker_size_m)

        import time as _time
        ts = ts if ts is not None else _time.time()

        out: dict[int, "_detection_module.PoseDetection"] = {}
        for d in detections:
            img_pts = d._raw_corners.reshape(-1, 1, 2).astype(np.float32)

            # Use solvePnP to estimate pose
            success, rvec, tvec = cv2.solvePnP(
                obj_pts, img_pts, K, dist, useExtrinsicGuess=False, flags=cv2.SOLVEPNP_EPNP
            )

            if not success:
                continue

            # Calculate reprojection error
            img_pts_proj, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist)
            error = cv2.norm(img_pts - img_pts_proj) / len(obj_pts)

            out[d.tag_id] = _detection_module.PoseDetection(
                tag_id=d.tag_id,
                rvec=np.asarray(rvec).reshape(3),
                tvec=np.asarray(tvec).reshape(3),
                reproj_error_px=float(error),
            )

        return out

    def get_dictionary_name(self) -> str:
        return "DICT_4X4_100"

    def dictionary_size(self) -> int:
        return 100

    @staticmethod
    def _marker_object_points(side_m: float) -> np.ndarray:
        """Standard marker corner template in marker frame."""
        half = side_m / 2.0
        return np.array(
            [
                [-half,  half, 0.0],
                [ half,  half, 0.0],
                [ half, -half, 0.0],
                [-half, -half, 0.0],
            ],
            dtype=np.float32,
        )


class DualDetector(BaseDetector):
    """Runs both AprilTag and ArUco detectors simultaneously for A/B testing."""

    def __init__(self, config: DetectorConfig):
        self.config = config
        self._apriltag = AprilTagDetector(config)
        self._aruco = ArUcoDetector(config)
        # Track which detector is primary for backwards compatibility
        self._primary = self._apriltag if config.detector_type == DetectorType.APRILTAG else self._aruco

    def detect(self, frame_bgr: np.ndarray) -> list["_detection_module.Detection"]:
        """Run both detectors and return combined results with source labels."""
        apriltag_detections = self._apriltag.detect(frame_bgr)
        aruco_detections = self._aruco.detect(frame_bgr)

        # Label detections with source for logging/analysis
        for d in apriltag_detections:
            d._source = "apriltag"  # type: ignore
        for d in aruco_detections:
            d._source = "aruco"  # type: ignore

        # Return primary detector results (could also merge both)
        return apriltag_detections

    def estimate_pose(
        self,
        detections: list["_detection_module.Detection"],
        K: np.ndarray,
        dist: np.ndarray,
        marker_size_m: float,
        *,
        filters: Optional[dict[int, "_detection_module._pose_filter.PoseFilter"]] = None,
        ts: Optional[float] = None,
    ) -> dict[int, "_detection_module.PoseDetection"]:
        """Use primary detector's pose estimation."""
        return self._primary.estimate_pose(detections, K, dist, marker_size_m, filters=filters, ts=ts)

    def get_dictionary_name(self) -> str:
        return self._primary.get_dictionary_name()

    def dictionary_size(self) -> int:
        return self._primary.dictionary_size()


def create_detector(config: DetectorConfig) -> BaseDetector:
    """Factory function to create appropriate detector instance."""
    if config.dual_detection_mode:
        return DualDetector(config)
    elif config.detector_type == DetectorType.APRILTAG:
        return AprilTagDetector(config)
    elif config.detector_type == DetectorType.ARUCO:
        return ArUcoDetector(config)
    else:
        raise ValueError(f"Unknown detector type: {config.detector_type}")
