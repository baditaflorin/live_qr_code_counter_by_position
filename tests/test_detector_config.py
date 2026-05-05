"""Tests for detector configuration system."""
import os
import tempfile
import pytest
from backend.detector_config import DetectorConfig, DetectorType, AprilTagConfig, ArUcoConfig, ConfigManager


def test_detector_config_defaults():
    """Test DetectorConfig with default values."""
    config = DetectorConfig()
    assert config.detector_type == DetectorType.APRILTAG
    assert config.marker_size_m == 0.05
    assert config.dual_detection_mode == False
    assert config.apriltag.quad_decimate == 4.0
    assert config.apriltag.nthreads == 4


def test_detector_config_serialization():
    """Test DetectorConfig to_dict and from_dict."""
    config = DetectorConfig(
        detector_type=DetectorType.ARUCO,
        marker_size_m=0.1,
        dual_detection_mode=True,
    )
    config_dict = config.to_dict()

    assert config_dict["detector_type"] == "aruco"
    assert config_dict["marker_size_m"] == 0.1
    assert config_dict["dual_detection_mode"] == True

    # Deserialize
    config2 = DetectorConfig.from_dict(config_dict)
    assert config2.detector_type == DetectorType.ARUCO
    assert config2.marker_size_m == 0.1
    assert config2.dual_detection_mode == True


def test_detector_config_load_from_env():
    """Test loading config from environment variables."""
    os.environ["DETECTOR_TYPE"] = "aruco"
    os.environ["MARKER_SIZE_M"] = "0.1"
    os.environ["DUAL_DETECTION_MODE"] = "true"
    os.environ["APRILTAG_QUAD_DECIMATE"] = "2.0"
    os.environ["ARUCO_WIN_SIZE_MIN"] = "10"

    config = DetectorConfig.load_from_env()
    assert config.detector_type == DetectorType.ARUCO
    assert config.marker_size_m == 0.1
    assert config.dual_detection_mode == True
    assert config.apriltag.quad_decimate == 2.0
    assert config.aruco.adaptiveThreshWinSizeMin == 10


def test_detector_config_disk_persistence():
    """Test saving and loading config from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = DetectorConfig(
            detector_type=DetectorType.ARUCO,
            marker_size_m=0.15,
            apriltag=AprilTagConfig(quad_decimate=2.5, nthreads=2),
        )

        # Save to disk
        config.save_to_disk(tmpdir)

        # Load from disk
        loaded_config = DetectorConfig.load_from_disk(tmpdir)
        assert loaded_config is not None
        assert loaded_config.detector_type == DetectorType.ARUCO
        assert loaded_config.marker_size_m == 0.15
        assert loaded_config.apriltag.quad_decimate == 2.5
        assert loaded_config.apriltag.nthreads == 2


def test_detector_config_load_from_disk_returns_none_if_not_exists():
    """Test that load_from_disk returns None if file doesn't exist."""
    config = DetectorConfig.load_from_disk("/nonexistent/path")
    assert config is None


def test_config_manager_thread_safety():
    """Test ConfigManager provides thread-safe config updates."""
    initial_config = DetectorConfig()
    manager = ConfigManager(initial_config)

    # Get config
    config1 = manager.get_config()
    assert config1.detector_type == DetectorType.APRILTAG

    # Update config
    new_config = DetectorConfig(detector_type=DetectorType.ARUCO)
    manager.set_config(new_config)

    # Get updated config
    config2 = manager.get_config()
    assert config2.detector_type == DetectorType.ARUCO


def test_config_manager_partial_update():
    """Test ConfigManager can update only specific fields."""
    initial_config = DetectorConfig()
    manager = ConfigManager(initial_config)

    # Update only detector_type
    updated = manager.update_config({"detector_type": "aruco", "marker_size_m": 0.2})
    assert updated.detector_type == DetectorType.ARUCO
    assert updated.marker_size_m == 0.2


def test_apriltag_config_parameters():
    """Test AprilTag configuration parameters."""
    config = AprilTagConfig(
        quad_decimate=1.5,
        quad_sigma=0.5,
        refine_edges=True,
        decode_sharpening=1.0,
        nthreads=2,
    )
    assert config.quad_decimate == 1.5
    assert config.quad_sigma == 0.5
    assert config.refine_edges == True
    assert config.decode_sharpening == 1.0
    assert config.nthreads == 2


def test_aruco_config_parameters():
    """Test ArUco configuration parameters."""
    config = ArUcoConfig(
        adaptiveThreshWinSizeMin=10,
        adaptiveThreshWinSizeMax=50,
        adaptiveThreshWinSizeStep=5,
        minMarkerPerimeterRate=0.05,
        cornerRefinementMethod="CORNER_REFINE_NONE",
    )
    assert config.adaptiveThreshWinSizeMin == 10
    assert config.adaptiveThreshWinSizeMax == 50
    assert config.adaptiveThreshWinSizeStep == 5
    assert config.minMarkerPerimeterRate == 0.05
    assert config.cornerRefinementMethod == "CORNER_REFINE_NONE"
