"""ADR 0050 — single-camera scene reconstruction.

Takes per-frame `(detection, pose)` pairs plus a world-frame extrinsic and
emits a `scene_world` payload of *people* in metres + degrees.  Multi-camera
fusion (the original ADR's "average across N cameras") collapses to identity
on the single-camera path the rest of the system runs on today; the same
function will do the right thing once a second camera is wired in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import pose as pose_mod
from .detection import Detection, PoseDetection


@dataclass
class MarkerObservation:
    aruco_id: int
    placement: str
    person_id: Optional[int]
    person_name: Optional[str]
    world_xyz: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    reproj_error_px: float


def build_marker_observations(
    detections: list[Detection],
    poses: dict[int, PoseDetection],
    extrinsic: pose_mod.Extrinsic,
    marker_meta: dict[int, dict],
) -> list[MarkerObservation]:
    """Combine 2D detection + camera-frame pose + world extrinsic.

    `marker_meta` maps `aruco_id` -> {"placement": ..., "person_id": ..., "person_name": ...}.
    """
    out: list[MarkerObservation] = []
    for d in detections:
        p = poses.get(d.aruco_id)
        if p is None:
            continue
        xyz_w, R_w = pose_mod.marker_pose_world(p.rvec, p.tvec, extrinsic)
        yaw, pitch, roll = pose_mod.R_to_euler_zyx_deg(R_w)
        meta = marker_meta.get(d.aruco_id, {})
        out.append(
            MarkerObservation(
                aruco_id=d.aruco_id,
                placement=meta.get("placement", "hat"),
                person_id=meta.get("person_id"),
                person_name=meta.get("person_name"),
                world_xyz=(float(xyz_w[0]), float(xyz_w[1]), float(xyz_w[2])),
                yaw_deg=yaw,
                pitch_deg=pitch,
                roll_deg=roll,
                reproj_error_px=p.reproj_error_px,
            )
        )
    return out


@dataclass
class PersonObservation:
    person_id: Optional[int]
    person_name: Optional[str]
    body_xyz: tuple[float, float, float]
    body_yaw_deg: float
    placements_seen: list[str]
    marker_ids: list[int]
    confidence: float


def _quality_weight(reproj_err_px: float) -> float:
    """High weight for low-error markers, asymptote to ~0 for trash detections."""
    return 1.0 / (0.25 + reproj_err_px * reproj_err_px)


def fuse_person_observations(markers: list[MarkerObservation]) -> list[PersonObservation]:
    """Group marker observations by person and produce one body-pose per person.

    ADR 0049 + 0050:
    * Position = quality-weighted average of marker world positions.
    * Body yaw is taken from the chest↔back vector when both are visible
      (most direct facing signal); otherwise from the chest marker; otherwise
      from the hat marker; otherwise from whatever single marker exists.
    """
    by_person: dict[Optional[int], list[MarkerObservation]] = {}
    for m in markers:
        by_person.setdefault(m.person_id, []).append(m)

    out: list[PersonObservation] = []
    for person_id, ms in by_person.items():
        if person_id is None:
            # Unassigned markers — emit one PersonObservation per marker so
            # they still show up in the 3D view but don't get fused with each
            # other (we genuinely don't know if two unassigned markers belong
            # to the same person).
            for m in ms:
                out.append(_singleton_person(m))
            continue

        weights = np.array([_quality_weight(m.reproj_error_px) for m in ms])
        positions = np.array([m.world_xyz for m in ms])
        wsum = float(weights.sum())
        if wsum <= 0:
            continue
        body_xyz = tuple(((positions.T * weights).sum(axis=1) / wsum).tolist())  # type: ignore

        yaw = _body_yaw_from_markers(ms)
        out.append(
            PersonObservation(
                person_id=person_id,
                person_name=ms[0].person_name,
                body_xyz=(body_xyz[0], body_xyz[1], body_xyz[2]),
                body_yaw_deg=yaw,
                placements_seen=sorted({m.placement for m in ms}),
                marker_ids=sorted({m.aruco_id for m in ms}),
                confidence=min(1.0, wsum / 4.0),  # 4 == "two ~0.5px-error markers"
            )
        )
    return out


def _singleton_person(m: MarkerObservation) -> PersonObservation:
    return PersonObservation(
        person_id=None,
        person_name=None,
        body_xyz=m.world_xyz,
        body_yaw_deg=m.yaw_deg,
        placements_seen=[m.placement],
        marker_ids=[m.aruco_id],
        confidence=min(1.0, _quality_weight(m.reproj_error_px) / 4.0),
    )


def _body_yaw_from_markers(ms: list[MarkerObservation]) -> float:
    """ADR 0049: chest↔back is the strongest yaw signal; fall back gracefully."""
    by_p = {m.placement: m for m in ms}
    chest = by_p.get("chest")
    back = by_p.get("back")
    if chest is not None and back is not None:
        # Person faces away from the back marker, toward the chest marker.
        dx = chest.world_xyz[0] - back.world_xyz[0]
        dy = chest.world_xyz[1] - back.world_xyz[1]
        if dx * dx + dy * dy > 1e-6:
            import math
            return math.degrees(math.atan2(dy, dx))
    if chest is not None:
        return chest.yaw_deg
    if back is not None:
        # Looking opposite to the back marker's own facing.
        return _wrap_deg(back.yaw_deg + 180.0)
    hat = by_p.get("hat")
    if hat is not None:
        return hat.yaw_deg
    return ms[0].yaw_deg


def _wrap_deg(a: float) -> float:
    return ((a + 180.0) % 360.0) - 180.0


# ---------- payload serialization ------------------------------------------

def serialize_marker(m: MarkerObservation) -> dict:
    return {
        "aruco_id": m.aruco_id,
        "placement": m.placement,
        "person_id": m.person_id,
        "person_name": m.person_name,
        "world_xyz_m": list(m.world_xyz),
        "yaw_deg":   round(m.yaw_deg,   2),
        "pitch_deg": round(m.pitch_deg, 2),
        "roll_deg":  round(m.roll_deg,  2),
        "reproj_error_px": round(m.reproj_error_px, 3),
    }


def serialize_person(p: PersonObservation) -> dict:
    return {
        "person_id": p.person_id,
        "person_name": p.person_name,
        "body_xyz_m": list(p.body_xyz),
        "body_yaw_deg": round(p.body_yaw_deg, 2),
        "placements_seen": p.placements_seen,
        "marker_ids": p.marker_ids,
        "confidence": round(p.confidence, 3),
    }
