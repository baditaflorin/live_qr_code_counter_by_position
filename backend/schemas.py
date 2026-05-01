from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PersonIn(BaseModel):
    name: str
    notes: Optional[str] = None


class PersonOut(BaseModel):
    id: int
    name: str
    notes: Optional[str] = None
    created_at: datetime
    marker_ids: list[int] = []

    class Config:
        from_attributes = True


class MarkerOut(BaseModel):
    aruco_id: int
    dictionary: str
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    placement: str = "hat"
    created_at: datetime


class MarkerCreateBatch(BaseModel):
    count: int = Field(gt=0, le=500)
    person_id: Optional[int] = None
    placement: str = "hat"


class MarkerAssign(BaseModel):
    person_id: Optional[int] = None
    placement: Optional[str] = None


class ZoneIn(BaseModel):
    name: str
    label: str = ""
    color: str = "#22c55e"
    polygon: list[list[float]]  # [[x,y], ...] normalized 0..1
    formation: Optional[str] = None
    locked: bool = False


class ZoneOut(BaseModel):
    id: int
    name: str
    label: str
    color: str
    polygon: list[list[float]]
    formation: Optional[str] = None
    locked: bool = False
    created_at: datetime


class ZonePatch(BaseModel):
    locked: Optional[bool] = None
    name: Optional[str] = None
    label: Optional[str] = None
    color: Optional[str] = None
    formation: Optional[str] = None


class QuestionIn(BaseModel):
    text: str
    block: Optional[str] = None
    formation: Optional[str] = None
    position: int = 0


class QuestionOut(BaseModel):
    id: int
    text: str
    is_active: bool
    block: Optional[str] = None
    formation: Optional[str] = None
    position: int = 0
    created_at: datetime


class QuestionBulkIn(BaseModel):
    questions: list[QuestionIn]
    replace_block: bool = False  # if true, delete existing rows in same block first


class VoteOut(BaseModel):
    id: int
    question_id: int
    snapshot_id: int
    marker_aruco_id: int
    zone_id: Optional[int]
    zone_label: Optional[str]
    person_id: Optional[int]
    person_name: Optional[str]
    recorded_at: datetime


class TrackingSessionIn(BaseModel):
    name: str
    proximity_norm: float = 0.12
    sample_interval_ms: int = 500


class TrackingSessionOut(BaseModel):
    id: int
    name: str
    proximity_norm: float
    sample_interval_ms: int
    started_at: datetime
    stopped_at: Optional[datetime] = None
    sample_count: int = 0
    markers_seen: int = 0


class TrackingReport(BaseModel):
    session: TrackingSessionOut
    duration_s: float
    sample_count: int
    snapshot_count: int
    markers_seen: list[int]
    pair_contact_seconds: list[dict]   # [{a, a_name, b, b_name, seconds}]
    never_met_pairs: list[dict]        # [{a, a_name, b, b_name}]
    per_person_contact_seconds: list[dict]  # [{aruco_id, person_name, seconds}]


# ---------- ADR 0048 / 0012 — camera intrinsic + extrinsic ----------------

class CameraOut(BaseModel):
    id: int
    name: str
    marker_size_m: float
    floor_rect_w_m: float
    floor_rect_h_m: float
    corner_ids: dict[str, int]
    intrinsic_calibrated: bool
    intrinsic_calibrated_at: Optional[datetime] = None
    intrinsic_reproj_error_px: Optional[float] = None
    intrinsic_image_w: Optional[int] = None
    intrinsic_image_h: Optional[int] = None
    extrinsic_calibrated: bool
    extrinsic_calibrated_at: Optional[datetime] = None
    extrinsic_reproj_error_px: Optional[float] = None
    K: Optional[list[list[float]]] = None
    dist: Optional[list[float]] = None
    R_world_to_camera: Optional[list[list[float]]] = None
    t_world_to_camera: Optional[list[float]] = None
    camera_position_world_m: Optional[list[float]] = None
    created_at: datetime


class CameraSettingsIn(BaseModel):
    """Operator-editable settings on a Camera row."""
    name: Optional[str] = None
    marker_size_m: Optional[float] = Field(default=None, gt=0.005, le=2.0)
    floor_rect_w_m: Optional[float] = Field(default=None, gt=0.1, le=50.0)
    floor_rect_h_m: Optional[float] = Field(default=None, gt=0.1, le=50.0)
    corner_ids: Optional[dict[str, int]] = None  # keys: tl/tr/br/bl


class CalibrationStatus(BaseModel):
    session_id: str
    camera_id: int
    views_accepted: int
    views_required: int
    ready: bool
    message: str


class ExtrinsicAutoIn(BaseModel):
    """Currently-detected pixel centers for the four floor-corner markers."""
    corners: dict[str, list[float]]  # {'tl': [px, py], ...}


# ---------- ADR 0021 / 0022 / 0073 — participant cards --------------------

class ParticipantCardIn(BaseModel):
    """Create / update a participant card.

    `params` is free-form per fire_model. For ``orientation`` it carries
    ``orientation_axis`` (yaw|pitch|roll), ``orientation_buckets`` (list of
    {center_deg, half_width_deg, value}), and optional stability tuning —
    see ADR 0073.
    """
    aruco_id: int = Field(ge=0, le=9999)
    name: str = ""
    kit: str = "reaction"
    action: str = ""
    fire_model: str = "pulse"  # pulse | level | gesture | orientation
    params: Optional[dict] = None
    enabled: bool = True


class ParticipantCardPatch(BaseModel):
    name: Optional[str] = None
    kit: Optional[str] = None
    action: Optional[str] = None
    fire_model: Optional[str] = None
    params: Optional[dict] = None
    enabled: Optional[bool] = None


class ParticipantCardOut(BaseModel):
    aruco_id: int
    name: str
    kit: str
    action: str
    fire_model: str
    params: dict = {}
    enabled: bool
    created_at: datetime


class ParticipantEventOut(BaseModel):
    id: int
    t: datetime
    marker_aruco_id: int
    held_by_aruco_id: Optional[int] = None
    kit: str
    action: str
    fire_model: str
    kind: str
    value: Optional[str] = None
    attribution_confidence: float
