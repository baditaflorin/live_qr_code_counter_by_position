import csv
import io
import json
import os
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import qrcode
from fastapi import (
    Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile,
    WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from . import (
    auth as auth_mod,
    badges as badge_gen,
    calibration as calibration_mod,
    control as control_mod,
    detection,
    drift as drift_mod,
    marker_tracker as tracker_mod,
    markers as marker_gen,
    observability as obs,
    pose as pose_mod,
    scene as scene_mod,
    tracking as tracking_mod,
)
from .db import (
    AuditLog, Camera, ControlMarker, Marker, Metric, Person, Question, SessionLocal,
    TrackingSample, TrackingSession, Vote, Zone, get_db, init_db,
)
from .schemas import (
    CalibrationStatus, CameraOut, CameraSettingsIn, ExtrinsicAutoIn,
    MarkerAssign, MarkerCreateBatch, MarkerOut, PersonIn, PersonOut, QuestionBulkIn,
    QuestionIn, QuestionOut, TrackingSessionIn, TrackingSessionOut, VoteOut,
    ZoneIn, ZoneOut, ZonePatch,
)
from .seeds.czocha_day1 import as_records as _czocha_day1_records
from .seeds.default_zones import records_for as _default_zones_records, DEFAULTS_BY_FORMATION

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="ArUco Counter")

# Auth middleware (ADR 0001). No-op when APP_TOKEN env var is unset, so
# existing deployments keep working until the operator opts in.
app.add_middleware(auth_mod.AuthMiddleware)

# Audit + request-id middleware (ADR 0009). Free of side-effects when the
# audited paths aren't hit.
app.add_middleware(obs.AuditMiddleware)


@app.on_event("startup")
async def _start_observability() -> None:
    obs.start_background_flush()


@app.on_event("shutdown")
async def _final_flush() -> None:
    obs.flush_now()


init_db()

# Seed default control markers (idempotent) so the 4 hands-free cards exist
# from the first boot. ADR 0011 + 0014.
def _seed_control_on_boot() -> None:
    db = SessionLocal()
    try:
        control_mod.seed_default_control_markers(db)
    finally:
        db.close()
_seed_control_on_boot()


# ---------- helpers ----------

def _person_to_out(p: Person) -> PersonOut:
    return PersonOut(
        id=p.id,
        name=p.name,
        notes=p.notes,
        created_at=p.created_at,
        marker_ids=[m.aruco_id for m in p.markers],
    )


def _marker_to_out(m: Marker) -> MarkerOut:
    return MarkerOut(
        aruco_id=m.aruco_id,
        dictionary=m.dictionary,
        person_id=m.person_id,
        person_name=m.person.name if m.person else None,
        placement=m.placement or "hat",
        created_at=m.created_at,
    )


VALID_PLACEMENTS = {"hat", "chest", "back", "wrist", "accessory"}


def _normalize_placement(p: Optional[str]) -> str:
    """ADR 0049 — coerce + validate the placement field."""
    if p is None:
        return "hat"
    p = p.strip().lower()
    if p not in VALID_PLACEMENTS:
        raise HTTPException(400, f"Invalid placement '{p}'. Allowed: {sorted(VALID_PLACEMENTS)}")
    return p


def _camera_to_out(c: Camera) -> CameraOut:
    cam_pos: Optional[list[float]] = None
    if c.has_extrinsic():
        try:
            ext = pose_mod.Extrinsic(
                R=np.array(c.R(), dtype=np.float64),
                t=np.array(c.t(), dtype=np.float64),
            )
            cam_pos = ext.camera_position_world().tolist()
        except Exception:
            cam_pos = None
    return CameraOut(
        id=c.id,
        name=c.name,
        marker_size_m=c.marker_size_m,
        floor_rect_w_m=c.floor_rect_w_m,
        floor_rect_h_m=c.floor_rect_h_m,
        corner_ids=c.corner_ids() or {},
        intrinsic_calibrated=c.has_intrinsic(),
        intrinsic_calibrated_at=c.intrinsic_calibrated_at,
        intrinsic_reproj_error_px=c.intrinsic_reproj_error_px,
        intrinsic_image_w=c.intrinsic_image_w,
        intrinsic_image_h=c.intrinsic_image_h,
        extrinsic_calibrated=c.has_extrinsic(),
        extrinsic_calibrated_at=c.extrinsic_calibrated_at,
        extrinsic_reproj_error_px=c.extrinsic_reproj_error_px,
        K=c.K(),
        dist=c.dist(),
        R_world_to_camera=c.R(),
        t_world_to_camera=c.t(),
        camera_position_world_m=cam_pos,
        created_at=c.created_at,
    )


def _zone_to_out(z: Zone) -> ZoneOut:
    return ZoneOut(
        id=z.id,
        name=z.name,
        label=z.label,
        color=z.color,
        polygon=z.points(),
        formation=z.formation,
        locked=bool(z.locked),
        created_at=z.created_at,
    )


def _question_to_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        text=q.text,
        is_active=bool(q.is_active),
        block=q.block,
        formation=q.formation,
        position=q.position or 0,
        created_at=q.created_at,
    )


def _next_aruco_id(db: Session) -> int:
    """Allocate the next person-marker id, skipping the reserved control range."""
    max_id = db.execute(select(func.max(Marker.aruco_id))).scalar()
    candidate = 0 if max_id is None else max_id + 1
    lo, hi = control_mod.control_id_range()
    # If the next candidate falls inside the reserved range, the dictionary
    # is exhausted for person markers — caller should switch ARUCO_DICTIONARY.
    if candidate >= lo:
        # Try to find the smallest unused id outside the reserved range.
        used = {row[0] for row in db.execute(select(Marker.aruco_id)).all()}
        for cand in range(0, lo):
            if cand not in used:
                return cand
        # Genuinely full.
        return candidate
    return candidate


# ---------- system info ----------

@app.get("/api/system")
def system_info():
    return {
        "dictionary": detection.get_dictionary_name(),
        "dictionary_size": detection.dictionary_size(),
        "data_dir": os.environ.get("DATA_DIR", "./data"),
    }


# ---------- people ----------

@app.get("/api/people", response_model=list[PersonOut])
def list_people(db: Session = Depends(get_db)):
    rows = db.execute(select(Person).options(joinedload(Person.markers))).unique().scalars().all()
    return [_person_to_out(p) for p in rows]


@app.post("/api/people", response_model=PersonOut)
def create_person(payload: PersonIn, db: Session = Depends(get_db)):
    p = Person(name=payload.name.strip(), notes=payload.notes)
    if not p.name:
        raise HTTPException(400, "Name required")
    db.add(p)
    db.commit()
    db.refresh(p)
    return _person_to_out(p)


@app.put("/api/people/{person_id}", response_model=PersonOut)
def update_person(person_id: int, payload: PersonIn, db: Session = Depends(get_db)):
    p = db.get(Person, person_id)
    if not p:
        raise HTTPException(404, "Not found")
    p.name = payload.name.strip()
    p.notes = payload.notes
    db.commit()
    db.refresh(p)
    return _person_to_out(p)


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    p = db.get(Person, person_id)
    if not p:
        raise HTTPException(404, "Not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- control markers (ADR 0011 + 0014) ----------

@app.get("/api/control-markers")
def list_control_markers(db: Session = Depends(get_db)):
    rows = db.execute(select(ControlMarker).order_by(ControlMarker.aruco_id)).scalars().all()
    lo, hi = control_mod.control_id_range()
    return {
        "reserved_range": [lo, hi],
        "known_actions": list(control_mod.KNOWN_ACTIONS),
        "markers": [
            {"aruco_id": m.aruco_id, "action": m.action, "label": m.label, "enabled": bool(m.enabled)}
            for m in rows
        ],
    }


@app.put("/api/control-markers/{aruco_id}")
def update_control_marker(aruco_id: int, payload: dict, db: Session = Depends(get_db)):
    m = db.get(ControlMarker, aruco_id)
    if not m:
        raise HTTPException(404, "Control marker not found")
    if "action" in payload:
        if payload["action"] not in control_mod.KNOWN_ACTIONS:
            raise HTTPException(400, f"Unknown action; one of {control_mod.KNOWN_ACTIONS}")
        m.action = payload["action"]
    if "label" in payload:
        m.label = str(payload["label"])[:120]
    if "enabled" in payload:
        m.enabled = 1 if payload["enabled"] else 0
    db.commit()
    return {"ok": True}


@app.get("/api/control-markers/pdf")
def control_markers_pdf(db: Session = Depends(get_db)):
    """Printable PDF — one large card per control marker with the action label."""
    rows = db.execute(select(ControlMarker).order_by(ControlMarker.aruco_id)).scalars().all()
    payload = [{"aruco_id": m.aruco_id, "label": f"{m.action}\n{m.label}"} for m in rows]
    if not payload:
        raise HTTPException(404, "No control markers configured")
    # Reuse the existing marker PDF generator — 2x2 layout for big cards.
    pdf_bytes = marker_gen.render_pdf(payload, cols=2, rows=2)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="control-cards.pdf"'},
    )


# ---------- CSV roster import ----------
#
# Implements ADR 0007. Required column: name. Optional: notes, marker_count
# (defaults to 1), tags (semicolon-separated, ignored for now — reserved for
# the participant-card kit's future per-person tagging).
#
# `dry_run=true` parses + validates without writing. `on_conflict` controls
# what to do when a name already exists: skip | merge | create.

def _parse_roster_csv(raw_bytes: bytes) -> list[dict]:
    """Tolerant CSV reader: BOM-stripped, comma + semicolon dialects, blank rows skipped."""
    text = raw_bytes.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
    except csv.Error:
        dialect = csv.excel  # fall back to comma
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows: list[dict] = []
    for raw in reader:
        # Lowercase + strip header keys.
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not row.get("name"):
            continue  # skip blank rows / header-only
        rows.append(row)
    return rows


def _next_aruco_ids(db: Session, n: int) -> list[int]:
    """Reserve N new marker ids; raises if dictionary capacity is exceeded."""
    dict_size = detection.dictionary_size()
    start = _next_aruco_id(db)
    if start + n > dict_size:
        remaining = max(0, dict_size - start)
        raise HTTPException(
            400,
            f"Dictionary {detection.get_dictionary_name()} only holds {dict_size} markers; "
            f"{n} more would overflow ({remaining} remaining). Switch ARUCO_DICTIONARY.",
        )
    return list(range(start, start + n))


@app.post("/api/people/import")
async def import_roster(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_conflict: str = Form("skip"),  # skip | merge | create
    db: Session = Depends(get_db),
):
    if on_conflict not in ("skip", "merge", "create"):
        raise HTTPException(400, "on_conflict must be skip | merge | create")

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV too large (>5 MB)")

    try:
        rows = _parse_roster_csv(raw)
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")

    if not rows:
        return {"ok": True, "rows": 0, "outcomes": [], "dry_run": dry_run}

    # Pre-compute requested marker count so we can fail fast on dictionary overflow.
    requested_markers = sum(max(0, _safe_int(r.get("marker_count"), 1)) for r in rows
                            if not (on_conflict == "skip"
                                    and _existing_person_by_name(db, r["name"])))

    if not dry_run and requested_markers > 0:
        # Just validate capacity; we'll allocate per-row inside the transaction.
        dict_size = detection.dictionary_size()
        next_id = _next_aruco_id(db)
        if next_id + requested_markers > dict_size:
            raise HTTPException(
                400,
                f"Need {requested_markers} marker ids; dictionary {detection.get_dictionary_name()} "
                f"has {max(0, dict_size - next_id)} remaining.",
            )

    outcomes: list[dict] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = row["name"]
        notes = row.get("notes") or None
        marker_count = max(0, _safe_int(row.get("marker_count"), 1))

        existing = _existing_person_by_name(db, name)

        try:
            if existing and on_conflict == "skip":
                outcomes.append({"row": i, "name": name, "status": "skipped",
                                 "person_id": existing.id,
                                 "marker_ids": [m.aruco_id for m in existing.markers]})
                continue

            if existing and on_conflict == "merge":
                if dry_run:
                    extra = max(0, marker_count - len(existing.markers))
                    outcomes.append({"row": i, "name": name, "status": "would_merge",
                                     "person_id": existing.id,
                                     "would_add_markers": extra})
                else:
                    extra = max(0, marker_count - len(existing.markers))
                    new_ids = _next_aruco_ids(db, extra) if extra else []
                    for mid in new_ids:
                        m = Marker(aruco_id=mid, dictionary=detection.get_dictionary_name(),
                                   person_id=existing.id)
                        db.add(m)
                        db.flush()
                    outcomes.append({"row": i, "name": name, "status": "merged",
                                     "person_id": existing.id, "marker_ids": new_ids})
                continue

            # create (either no existing, or on_conflict == create which always creates).
            if dry_run:
                outcomes.append({"row": i, "name": name, "status": "would_create",
                                 "would_create_markers": marker_count})
            else:
                p = Person(name=name, notes=notes)
                db.add(p)
                db.flush()
                new_ids = _next_aruco_ids(db, marker_count) if marker_count else []
                for mid in new_ids:
                    m = Marker(aruco_id=mid, dictionary=detection.get_dictionary_name(),
                               person_id=p.id)
                    db.add(m)
                    db.flush()
                outcomes.append({"row": i, "name": name, "status": "created",
                                 "person_id": p.id, "marker_ids": new_ids})
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:  # noqa: BLE001
            db.rollback()
            outcomes.append({"row": i, "name": name, "status": "error", "error": str(e)})
            return {"ok": False, "rows": len(rows), "outcomes": outcomes, "dry_run": dry_run}

    if not dry_run:
        db.commit()

    return {"ok": True, "rows": len(rows), "outcomes": outcomes, "dry_run": dry_run}


def _safe_int(s: Optional[str], default: int) -> int:
    if s is None or s == "":
        return default
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return default


def _existing_person_by_name(db: Session, name: str) -> Optional[Person]:
    return db.execute(
        select(Person).options(joinedload(Person.markers)).where(Person.name == name)
    ).unique().scalars().first()


# ---------- markers ----------

@app.get("/api/markers", response_model=list[MarkerOut])
def list_markers(db: Session = Depends(get_db)):
    rows = (
        db.execute(select(Marker).options(joinedload(Marker.person)).order_by(Marker.aruco_id))
        .scalars()
        .all()
    )
    return [_marker_to_out(m) for m in rows]


@app.post("/api/markers/batch", response_model=list[MarkerOut])
def create_marker_batch(payload: MarkerCreateBatch, db: Session = Depends(get_db)):
    if payload.person_id is not None:
        if not db.get(Person, payload.person_id):
            raise HTTPException(400, "Unknown person_id")
    dict_size = detection.dictionary_size()
    person_ceiling = dict_size - control_mod.CONTROL_RESERVED_COUNT
    next_id = _next_aruco_id(db)
    if next_id + payload.count > person_ceiling:
        remaining = max(0, person_ceiling - next_id)
        raise HTTPException(
            400,
            f"Dictionary {detection.get_dictionary_name()} has {person_ceiling} person-marker slots "
            f"(top {control_mod.CONTROL_RESERVED_COUNT} reserved for control cards). "
            f"Next id is {next_id}, only {remaining} remaining. "
            f"Switch ARUCO_DICTIONARY to a larger one (e.g. DICT_4X4_250) and rebuild.",
        )
    placement = _normalize_placement(payload.placement)
    created: list[Marker] = []
    for _ in range(payload.count):
        new_id = _next_aruco_id(db)
        m = Marker(
            aruco_id=new_id,
            dictionary=detection.get_dictionary_name(),
            person_id=payload.person_id,
            placement=placement,
        )
        db.add(m)
        db.flush()
        created.append(m)
    db.commit()
    return [_marker_to_out(m) for m in created]


@app.put("/api/markers/{aruco_id}/assign", response_model=MarkerOut)
def assign_marker(aruco_id: int, payload: MarkerAssign, db: Session = Depends(get_db)):
    m = db.get(Marker, aruco_id)
    if not m:
        raise HTTPException(404, "Marker not found")
    if payload.person_id is not None and not db.get(Person, payload.person_id):
        raise HTTPException(400, "Unknown person_id")
    m.person_id = payload.person_id
    if payload.placement is not None:
        m.placement = _normalize_placement(payload.placement)
    db.commit()
    db.refresh(m)
    return _marker_to_out(m)


@app.delete("/api/markers/{aruco_id}")
def delete_marker(aruco_id: int, db: Session = Depends(get_db)):
    m = db.get(Marker, aruco_id)
    if not m:
        raise HTTPException(404, "Marker not found")
    db.delete(m)
    db.commit()
    return {"ok": True}


@app.get("/api/markers/{aruco_id}/image")
def marker_image(aruco_id: int, db: Session = Depends(get_db)):
    if not db.get(Marker, aruco_id):
        raise HTTPException(404, "Marker not found")
    if aruco_id >= detection.dictionary_size():
        raise HTTPException(
            409,
            f"Marker id {aruco_id} is outside dictionary {detection.get_dictionary_name()}. "
            f"Delete it or switch dictionaries.",
        )
    png = marker_gen.render_marker_png(aruco_id)
    return Response(content=png, media_type="image/png")


@app.get("/api/badge-styles")
def badge_styles():
    """Catalog of available badge templates / palettes / cell ornaments / generative frames."""
    return {
        "templates": list(badge_gen.TEMPLATE_LAYOUTS.keys()),
        "palettes": [
            {
                "name": p.name,
                "ink": "#%02x%02x%02x" % p.ink,
                "paper": "#%02x%02x%02x" % p.paper,
                "accent": "#%02x%02x%02x" % p.accent,
                "contrast_ratio": round(p.contrast_ratio(), 2),
            }
            for p in badge_gen.PALETTES.values()
        ],
        "cell_styles": list(badge_gen.CELL_STYLES),
        "cell_min_px": badge_gen.CELL_MIN_PX_PER_SIDE,
        "frames": list(badge_gen.FRAME_GENERATORS.keys()),
    }


@app.get("/api/markers/{aruco_id}/badge")
def marker_badge(
    aruco_id: int,
    template: str = "default",
    palette: str = "default",
    cell_style: str = "square",
    frame: str = "none",
    sigil: Optional[str] = None,
    width: int = 1000,
    height: int = 1300,
    verify: bool = False,
    db: Session = Depends(get_db),
):
    """Render a styled badge for the given marker. Returns a PNG.

    Implements ADRs 0068 (composition) + 0069 (cell ornament) + 0070 (palette)
    + 0071 (generative frame). The marker stays detectable regardless of style.
    """
    m = db.get(Marker, aruco_id)
    if not m:
        raise HTTPException(404, "Marker not found")
    if aruco_id >= detection.dictionary_size():
        raise HTTPException(409, f"Marker id {aruco_id} is outside dictionary {detection.get_dictionary_name()}.")

    name = m.person.name if m.person else ""
    opts = badge_gen.BadgeOptions(
        template=template,
        palette=palette,
        cell_style=cell_style,
        frame=frame,
        sigil=sigil,
        badge_w=max(200, min(width, 2000)),
        badge_h=max(200, min(height, 2400)),
    )

    try:
        if verify:
            result = badge_gen.verify_detection(aruco_id, opts)
            if not result["ok"]:
                raise HTTPException(409, f"Detection verification failed: {result}")
        png = badge_gen.render_badge_png(aruco_id, name, opts)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(content=png, media_type="image/png")


@app.get("/api/markers/pdf")
def markers_pdf(
    ids: Optional[str] = Query(None, description="comma-separated aruco ids"),
    cols: int = 3,
    rows: int = 3,
    db: Session = Depends(get_db),
):
    if ids:
        try:
            id_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(400, "Invalid ids")
        rows_q = (
            db.execute(
                select(Marker)
                .options(joinedload(Marker.person))
                .where(Marker.aruco_id.in_(id_list))
                .order_by(Marker.aruco_id)
            )
            .scalars()
            .all()
        )
    else:
        rows_q = (
            db.execute(select(Marker).options(joinedload(Marker.person)).order_by(Marker.aruco_id))
            .scalars()
            .all()
        )

    payload = [
        {
            "aruco_id": m.aruco_id,
            "label": m.person.name if m.person else "",
        }
        for m in rows_q
    ]
    pdf_bytes = marker_gen.render_pdf(payload, cols=cols, rows=rows)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="markers.pdf"'},
    )


# ---------- system limits / health (ADR 0035) ----------

@app.get("/api/system/limits")
def system_limits(db: Session = Depends(get_db)):
    """Documented envelope + last observed values for each limit. Each row
    has a green/yellow/red verdict so the operator can see at a glance
    whether the system is in spec right now."""
    obs.flush_now()
    cutoff_60s = datetime.utcnow() - timedelta(seconds=60)
    cutoff_5m  = datetime.utcnow() - timedelta(minutes=5)

    # Observed values from the metrics buffer.
    median_detect_ms = _median_metric(db, "detection.latency_ms", cutoff_60s)
    median_bandwidth = _median_metric(db, "ws.bandwidth_mbps",   cutoff_60s)
    last_report_ms   = _last_metric(  db, "db.report_compute_ms",cutoff_5m)
    ghost_count_60s  = _sum_metric(   db, "detection.ghosts",    cutoff_60s)

    # Static configuration / capacity.
    dict_size = detection.dictionary_size()
    person_ceiling = dict_size - control_mod.CONTROL_RESERVED_COUNT
    next_id = _next_aruco_id(db)
    person_used = next_id
    sample_total = db.execute(select(func.count(TrackingSample.id))).scalar() or 0

    rows = [
        _limit_row(
            "Person-marker capacity",
            f"{person_used} / {person_ceiling}",
            ratio=person_used / max(1, person_ceiling),
            warn_at=0.8, fail_at=0.97,
            hint=f"Top {control_mod.CONTROL_RESERVED_COUNT} ids are reserved for control markers (ADR 0011).",
        ),
        _limit_row(
            "Dictionary",
            f"{detection.get_dictionary_name()} ({dict_size} ids)",
            ratio=0.0, warn_at=2.0, fail_at=2.0,  # always green; informational
            hint="Set ARUCO_DICTIONARY env to switch.",
        ),
        _limit_row(
            "Detection latency (60s median)",
            f"{median_detect_ms:.0f} ms" if median_detect_ms is not None else "—",
            ratio=(median_detect_ms or 0) / 100.0,
            warn_at=0.5, fail_at=1.0,  # 50ms yellow, 100ms red
            hint="Detection per frame should stay under 50 ms at 1080p.",
        ),
        _limit_row(
            "WS upstream bandwidth (60s median)",
            f"{median_bandwidth:.1f} Mbps" if median_bandwidth is not None else "—",
            ratio=(median_bandwidth or 0) / 30.0,
            warn_at=0.6, fail_at=0.9,  # >18 Mbps yellow, >27 Mbps red on typical Wi-Fi
            hint="Most venue Wi-Fi caps around 30 Mbps upstream per client.",
        ),
        _limit_row(
            "Report compute (last 5min)",
            f"{last_report_ms:.0f} ms" if last_report_ms is not None else "—",
            ratio=(last_report_ms or 0) / 5000.0,
            warn_at=0.6, fail_at=1.0,  # 3s yellow, 5s red
            hint="Long compute usually means tracking_samples needs pruning.",
        ),
        _limit_row(
            "Tracking samples (lifetime)",
            f"{sample_total:,}",
            ratio=sample_total / 20_000_000.0,  # 20M soft limit on SQLite
            warn_at=0.5, fail_at=0.9,
            hint="SQLite slows past ~20 M rows; prune via retention (ADR 0010).",
        ),
        _limit_row(
            "Marker ghost frames (60s)",
            f"{ghost_count_60s:.0f}" if ghost_count_60s is not None else "0",
            ratio=(ghost_count_60s or 0) / 600.0,
            warn_at=0.5, fail_at=1.0,
            hint="High counts = detection is unreliable; check lighting / marker size (ADR 0031).",
        ),
    ]
    return {
        "observed_at": datetime.utcnow().isoformat(),
        "rows": rows,
        "overall": _overall_verdict([r["verdict"] for r in rows]),
    }


def _median_metric(db: Session, name: str, since: datetime) -> Optional[float]:
    rows = db.execute(
        select(Metric.value).where(Metric.name == name, Metric.t >= since)
    ).scalars().all()
    if not rows:
        return None
    rows = sorted(rows)
    n = len(rows)
    return rows[n // 2] if n % 2 else (rows[n // 2 - 1] + rows[n // 2]) / 2


def _last_metric(db: Session, name: str, since: datetime) -> Optional[float]:
    r = db.execute(
        select(Metric.value).where(Metric.name == name, Metric.t >= since)
        .order_by(Metric.t.desc()).limit(1)
    ).scalar()
    return float(r) if r is not None else None


def _sum_metric(db: Session, name: str, since: datetime) -> Optional[float]:
    r = db.execute(
        select(func.sum(Metric.value)).where(Metric.name == name, Metric.t >= since)
    ).scalar()
    return float(r) if r is not None else None


def _limit_row(label: str, value: str, ratio: float, warn_at: float, fail_at: float, hint: str) -> dict:
    if ratio >= fail_at:
        verdict = "red"
    elif ratio >= warn_at:
        verdict = "yellow"
    else:
        verdict = "green"
    return {"label": label, "value": value, "verdict": verdict, "hint": hint}


def _overall_verdict(verdicts: list[str]) -> str:
    if "red" in verdicts:
        return "red"
    if "yellow" in verdicts:
        return "yellow"
    return "green"


# ---------- observability surfaces (ADR 0009 + 0036) ----------

@app.get("/api/metrics")
def get_metrics(
    name: Optional[str] = None,
    since_minutes: int = 60,
    limit: int = 5000,
    db: Session = Depends(get_db),
):
    """Recent metrics. `name=detection.markers_seen&since_minutes=10` for a
    focused query, omit `name` for a unique-name list with last value."""
    obs.flush_now()  # ensure recent recordings are visible
    cutoff = datetime.utcnow() - timedelta(minutes=max(1, min(since_minutes, 7 * 24 * 60)))
    if name:
        rows = (
            db.execute(
                select(Metric).where(Metric.name == name, Metric.t >= cutoff)
                .order_by(Metric.t.desc()).limit(limit)
            )
            .scalars().all()
        )
        return {
            "name": name,
            "samples": [
                {
                    "t": r.t.isoformat(),
                    "value": r.value,
                    "tags": json.loads(r.tags_json) if r.tags_json else {},
                }
                for r in rows
            ],
        }
    # Summary view: per-metric count + last value.
    summary = db.execute(
        select(Metric.name, func.count(Metric.id), func.max(Metric.t))
        .where(Metric.t >= cutoff)
        .group_by(Metric.name)
        .order_by(Metric.name)
    ).all()
    return {
        "since": cutoff.isoformat(),
        "metrics": [
            {"name": n, "count": int(c), "last_seen": (t.isoformat() if t else None)}
            for n, c, t in summary
        ],
    }


@app.get("/api/audit")
def get_audit_log(
    since_minutes: int = 60,
    method: Optional[str] = None,
    path_prefix: Optional[str] = None,
    actor: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    obs.flush_now()
    cutoff = datetime.utcnow() - timedelta(minutes=max(1, min(since_minutes, 30 * 24 * 60)))
    stmt = select(AuditLog).where(AuditLog.t >= cutoff)
    if method:
        stmt = stmt.where(AuditLog.method == method.upper())
    if path_prefix:
        stmt = stmt.where(AuditLog.path.like(f"{path_prefix}%"))
    if actor:
        stmt = stmt.where(AuditLog.actor_token_hash == actor)
    rows = db.execute(stmt.order_by(AuditLog.t.desc()).limit(limit)).scalars().all()
    return {
        "since": cutoff.isoformat(),
        "rows": [
            {
                "t": r.t.isoformat(),
                "actor": r.actor_token_hash,
                "method": r.method,
                "path": r.path,
                "query": r.query,
                "status": r.status_code,
                "request_id": r.request_id,
                "duration_ms": r.duration_ms,
            }
            for r in rows
        ],
    }


# ---------- resolution / marker-size feasibility (ADR 0031) ----------

@app.get("/api/feasibility")
def feasibility(
    image_w_px: int = 1920,
    image_h_px: int = 1080,
    marker_size_m: float = 0.15,
    floor_w_m: float = 5.0,
    floor_h_m: float = 4.0,
):
    """Pure-math estimate of pixels-per-marker-side at the corners of a
    rectangular floor area. Surfaces the per-cell threshold from ADR 0031
    so the operator can see whether their setup will detect cleanly before
    they show up at the venue.

    The floor is assumed to fill the camera's view roughly at center and
    pinch-toward-the-back per ADR 0003's homography. We approximate corners
    as 0.7× and 1.0× of the centre's pixels-per-metre — accurate enough to
    surface a 'this won't detect at the back' warning, not for fine work.
    """
    if image_w_px <= 0 or image_h_px <= 0 or marker_size_m <= 0 or floor_w_m <= 0:
        raise HTTPException(400, "All dimensions must be positive")
    # Pixels per metre at frame centre, assuming the floor fills frame width.
    px_per_m_centre = image_w_px / floor_w_m
    # Marker pixel side at the centre (roughly), and at the foreshortened back edge.
    centre_px = px_per_m_centre * marker_size_m
    back_px = centre_px * 0.65   # back edge — perspective makes markers smaller
    front_px = centre_px * 1.05  # front edge — slightly bigger

    from .badges import CELL_MIN_PX_PER_SIDE
    per_cell_recommendations = CELL_MIN_PX_PER_SIDE

    # 40 px per marker side is the conservative floor.
    PERSON_FLOOR = 40
    ok_centre = centre_px >= PERSON_FLOOR
    ok_back   = back_px   >= PERSON_FLOOR
    verdict = (
        "comfortable" if ok_back and back_px >= 60 else
        "marginal"    if ok_back else
        "back-of-room won't detect; print bigger markers or add a camera"
    )

    return {
        "image_size_px": [image_w_px, image_h_px],
        "marker_size_m": marker_size_m,
        "floor_size_m": [floor_w_m, floor_h_m],
        "px_per_marker_side": {
            "front":  round(front_px,  1),
            "centre": round(centre_px, 1),
            "back":   round(back_px,   1),
        },
        "person_floor_px": PERSON_FLOOR,
        "verdict": verdict,
        "per_cell_min_px": per_cell_recommendations,
        "advice": [
            "Centre detects fine if you see ≥ 40 px/marker; ≥ 60 px is comfortable.",
            "If the back of the room scores < 40, options: (1) print bigger markers, "
            "(2) higher camera resolution (4K), (3) add a second camera covering the back.",
            "Stylised cell ornaments (hexagon/six_star/leaf/rosette) need 50–60+ px per side.",
        ],
    }


# ---------- cameras + calibration (ADR 0048 + 0012) ----------

@app.get("/api/cameras", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    rows = db.execute(select(Camera).order_by(Camera.id)).scalars().all()
    return [_camera_to_out(c) for c in rows]


@app.get("/api/cameras/{camera_id}", response_model=CameraOut)
def get_camera(camera_id: int, db: Session = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    return _camera_to_out(c)


@app.put("/api/cameras/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: int, payload: CameraSettingsIn, db: Session = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    if payload.name is not None:
        c.name = payload.name.strip() or c.name
    if payload.marker_size_m is not None:
        c.marker_size_m = float(payload.marker_size_m)
    if payload.floor_rect_w_m is not None:
        c.floor_rect_w_m = float(payload.floor_rect_w_m)
    if payload.floor_rect_h_m is not None:
        c.floor_rect_h_m = float(payload.floor_rect_h_m)
    if payload.corner_ids is not None:
        for k in ("tl", "tr", "br", "bl"):
            if k not in payload.corner_ids:
                raise HTTPException(400, f"corner_ids missing key '{k}'")
        c.corner_ids_json = json.dumps({k: int(payload.corner_ids[k]) for k in ("tl", "tr", "br", "bl")})
    db.commit()
    db.refresh(c)
    return _camera_to_out(c)


@app.delete("/api/cameras/{camera_id}/intrinsic")
def clear_intrinsic(camera_id: int, db: Session = Depends(get_db)):
    """Forget the intrinsic calibration — operator will redo ChArUco capture."""
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    c.K_json = None
    c.dist_json = None
    c.intrinsic_calibrated_at = None
    c.intrinsic_reproj_error_px = None
    c.intrinsic_image_w = None
    c.intrinsic_image_h = None
    # Extrinsic depends on intrinsic, so clear it too.
    c.extrinsic_R_json = None
    c.extrinsic_t_json = None
    c.extrinsic_calibrated_at = None
    c.extrinsic_reproj_error_px = None
    db.commit()
    return {"ok": True}


@app.delete("/api/cameras/{camera_id}/extrinsic")
def clear_extrinsic(camera_id: int, db: Session = Depends(get_db)):
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    c.extrinsic_R_json = None
    c.extrinsic_t_json = None
    c.extrinsic_calibrated_at = None
    c.extrinsic_reproj_error_px = None
    db.commit()
    return {"ok": True}


@app.get("/api/calibration/charuco-board.png")
def charuco_board_png(size_px: int = 1500):
    png = pose_mod.render_charuco_board_png(detection.get_dictionary(), size_px=size_px)
    return Response(content=png, media_type="image/png")


@app.get("/api/calibration/charuco-qr")
def charuco_qr(request: Request):
    """QR code that opens the fullscreen /charuco tablet page."""
    base = str(request.base_url).rstrip("/")
    url = f"{base}/charuco"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/cameras/{camera_id}/calibration/intrinsic/start", response_model=CalibrationStatus)
def start_intrinsic_calibration(camera_id: int, db: Session = Depends(get_db)):
    if not db.get(Camera, camera_id):
        raise HTTPException(404, "Camera not found")
    sess = calibration_mod.start_session(camera_id)
    return CalibrationStatus(**sess.status())


@app.get("/api/cameras/{camera_id}/calibration/intrinsic/{session_id}", response_model=CalibrationStatus)
def get_intrinsic_status(camera_id: int, session_id: str):
    sess = calibration_mod.get_session(session_id)
    if not sess or sess.camera_id != camera_id:
        raise HTTPException(404, "Calibration session not found")
    return CalibrationStatus(**sess.status())


@app.post("/api/cameras/{camera_id}/calibration/intrinsic/{session_id}/frame", response_model=CalibrationStatus)
async def add_intrinsic_frame(camera_id: int, session_id: str, request: Request):
    """Accept one JPEG frame (raw bytes in body).  Stateless from the caller's
    point of view — the server tracks accepted views in the session."""
    sess = calibration_mod.get_session(session_id)
    if not sess or sess.camera_id != camera_id:
        raise HTTPException(404, "Calibration session not found")
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "Empty frame body")
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Could not decode JPEG")
    status = calibration_mod.add_frame(session_id, frame)
    if "error" in status:
        raise HTTPException(400, status["error"])
    return CalibrationStatus(**status)


@app.post("/api/cameras/{camera_id}/calibration/intrinsic/{session_id}/finish")
def finish_intrinsic_calibration(camera_id: int, session_id: str, db: Session = Depends(get_db)):
    sess = calibration_mod.get_session(session_id)
    if not sess or sess.camera_id != camera_id:
        raise HTTPException(404, "Calibration session not found")
    result = calibration_mod.finish(session_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.delete("/api/cameras/{camera_id}/calibration/intrinsic/{session_id}")
def cancel_intrinsic_calibration(camera_id: int, session_id: str):
    calibration_mod.discard_session(session_id)
    return {"ok": True}


@app.post("/api/cameras/{camera_id}/calibration/extrinsic/auto")
def auto_calibrate_extrinsic(camera_id: int, payload: ExtrinsicAutoIn, db: Session = Depends(get_db)):
    """ADR 0012 — solve extrinsic from the four floor-corner markers.

    The browser submits the *current pixel centers* of the four corner
    markers (from the live detection overlay).  This way the calibration
    happens with the exact same lens that streams frames live.
    """
    c = db.get(Camera, camera_id)
    if not c:
        raise HTTPException(404, "Camera not found")
    if not c.has_intrinsic():
        raise HTTPException(409, "Run intrinsic calibration first.")
    centers: dict[str, tuple[float, float]] = {}
    for k, v in payload.corners.items():
        if k not in ("tl", "tr", "br", "bl"):
            continue
        if not isinstance(v, list) or len(v) != 2:
            continue
        centers[k] = (float(v[0]), float(v[1]))
    result = calibration_mod.calibrate_extrinsic(db, camera_id, centers)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ---------- zones ----------

@app.get("/api/zones", response_model=list[ZoneOut])
def list_zones(formation: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(Zone).order_by(Zone.formation.is_(None).desc(), Zone.formation.asc(), Zone.id.asc())
    if formation:
        stmt = select(Zone).where(Zone.formation == formation).order_by(Zone.id)
    rows = db.execute(stmt).scalars().all()
    return [_zone_to_out(z) for z in rows]


@app.post("/api/zones", response_model=ZoneOut)
def create_zone(payload: ZoneIn, db: Session = Depends(get_db)):
    if len(payload.polygon) < 3:
        raise HTTPException(400, "Polygon needs at least 3 points")
    z = Zone(
        name=payload.name.strip() or "Zone",
        label=payload.label.strip(),
        color=payload.color,
        polygon=json.dumps(payload.polygon),
        formation=(payload.formation or None),
        locked=1 if payload.locked else 0,
    )
    db.add(z)
    db.commit()
    db.refresh(z)
    return _zone_to_out(z)


@app.put("/api/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: int, payload: ZoneIn, db: Session = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    if z.locked:
        raise HTTPException(409, "Zone is locked. Unlock it before editing.")
    if len(payload.polygon) < 3:
        raise HTTPException(400, "Polygon needs at least 3 points")
    z.name = payload.name.strip() or "Zone"
    z.label = payload.label.strip()
    z.color = payload.color
    z.polygon = json.dumps(payload.polygon)
    z.formation = payload.formation or None
    z.locked = 1 if payload.locked else 0
    db.commit()
    db.refresh(z)
    return _zone_to_out(z)


@app.patch("/api/zones/{zone_id}", response_model=ZoneOut)
def patch_zone(zone_id: int, payload: ZonePatch, db: Session = Depends(get_db)):
    """Partial update — primarily for the lock toggle from the zones list.

    Polygon edits go through PUT (and respect the lock); this endpoint lets
    you flip `locked` on a zone that is currently locked, and tweak metadata
    fields without re-uploading the whole polygon.
    """
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    if payload.locked is not None:
        z.locked = 1 if payload.locked else 0
    if payload.name is not None:
        z.name = payload.name.strip() or z.name
    if payload.label is not None:
        z.label = payload.label.strip()
    if payload.color is not None:
        z.color = payload.color
    if payload.formation is not None:
        z.formation = payload.formation or None
    db.commit()
    db.refresh(z)
    return _zone_to_out(z)


@app.delete("/api/zones/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(404, "Zone not found")
    db.delete(z)
    db.commit()
    return {"ok": True}


@app.post("/api/zones/seed/defaults", response_model=list[ZoneOut])
def seed_default_zones(
    formations: Optional[str] = None,
    replace: bool = True,
    db: Session = Depends(get_db),
):
    """Drop default zone polygons for each formation. Pass `formations=line,two_camps` to limit."""
    keys = [k.strip() for k in formations.split(",")] if formations else None
    records = _default_zones_records(keys)
    if replace:
        target = {r["formation"] for r in records}
        if target:
            db.query(Zone).filter(Zone.formation.in_(target)).delete(synchronize_session=False)
    created: list[Zone] = []
    for r in records:
        z = Zone(
            name=r["name"],
            label=r["label"],
            color=r["color"],
            polygon=json.dumps(r["polygon"]),
            formation=r["formation"],
        )
        db.add(z)
        created.append(z)
    db.commit()
    for z in created:
        db.refresh(z)
    return [_zone_to_out(z) for z in created]


# ---------- questions / votes ----------

@app.get("/api/questions", response_model=list[QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    # Order: block (asc, NULLs first), then position, then id — gives a stable
    # facilitator-friendly sequence when running through a deck.
    rows = db.execute(
        select(Question).order_by(
            Question.block.is_(None).desc(),
            Question.block.asc(),
            Question.position.asc(),
            Question.id.asc(),
        )
    ).scalars().all()
    return [_question_to_out(q) for q in rows]


@app.post("/api/questions", response_model=QuestionOut)
def create_question(payload: QuestionIn, db: Session = Depends(get_db)):
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Text required")
    q = Question(
        text=text,
        block=(payload.block or None),
        formation=(payload.formation or None),
        position=payload.position or 0,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_to_out(q)


@app.put("/api/questions/{question_id}", response_model=QuestionOut)
def update_question(question_id: int, payload: QuestionIn, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Not found")
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Text required")
    q.text = text
    q.block = payload.block or None
    q.formation = payload.formation or None
    q.position = payload.position or 0
    db.commit()
    db.refresh(q)
    return _question_to_out(q)


@app.post("/api/questions/bulk", response_model=list[QuestionOut])
def bulk_create_questions(payload: QuestionBulkIn, db: Session = Depends(get_db)):
    if payload.replace_block:
        blocks_to_clear = {q.block for q in payload.questions if q.block}
        if blocks_to_clear:
            db.query(Question).filter(Question.block.in_(blocks_to_clear)).delete(
                synchronize_session=False
            )
    created: list[Question] = []
    for spec in payload.questions:
        text = spec.text.strip()
        if not text:
            continue
        q = Question(
            text=text,
            block=(spec.block or None),
            formation=(spec.formation or None),
            position=spec.position or 0,
        )
        db.add(q)
        created.append(q)
    db.commit()
    for q in created:
        db.refresh(q)
    return [_question_to_out(q) for q in created]


@app.post("/api/questions/seed/czocha-day-1")
def seed_czocha_day_1(
    replace: bool = True,
    include_zones: bool = True,
    db: Session = Depends(get_db),
):
    """Load the Czocha Day 1 deck (questions) and the matching default zone templates."""
    records = _czocha_day1_records()
    if replace:
        blocks = {r["block"] for r in records if r.get("block")}
        if blocks:
            db.query(Question).filter(Question.block.in_(blocks)).delete(
                synchronize_session=False
            )
    created_q: list[Question] = []
    for r in records:
        q = Question(
            text=r["text"],
            block=r.get("block"),
            formation=r.get("formation"),
            position=r.get("position") or 0,
        )
        db.add(q)
        created_q.append(q)
    db.commit()
    for q in created_q:
        db.refresh(q)

    created_z: list[Zone] = []
    if include_zones:
        # Seed default zones only for the formations actually used in this deck.
        used = sorted({r["formation"] for r in records if r.get("formation")})
        zone_records = _default_zones_records(used)
        target = {r["formation"] for r in zone_records}
        if target:
            db.query(Zone).filter(Zone.formation.in_(target)).delete(synchronize_session=False)
        for zr in zone_records:
            z = Zone(
                name=zr["name"], label=zr["label"], color=zr["color"],
                polygon=json.dumps(zr["polygon"]), formation=zr["formation"],
            )
            db.add(z)
            created_z.append(z)
        db.commit()
        for z in created_z:
            db.refresh(z)

    return {
        "questions": [_question_to_out(q).model_dump() for q in created_q],
        "zones":     [_zone_to_out(z).model_dump() for z in created_z],
    }


@app.put("/api/questions/{question_id}/activate", response_model=QuestionOut)
def activate_question(question_id: int, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Not found")
    db.query(Question).update({Question.is_active: 0})
    q.is_active = 1
    db.commit()
    db.refresh(q)
    return _question_to_out(q)


@app.put("/api/questions/deactivate-all")
def deactivate_all(db: Session = Depends(get_db)):
    db.query(Question).update({Question.is_active: 0})
    db.commit()
    return {"ok": True}


@app.delete("/api/questions/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Not found")
    db.delete(q)
    db.commit()
    return {"ok": True}


@app.get("/api/questions/active", response_model=Optional[QuestionOut])
def get_active(db: Session = Depends(get_db)):
    q = db.execute(select(Question).where(Question.is_active == 1)).scalars().first()
    return _question_to_out(q) if q else None


@app.post("/api/questions/{question_id}/snapshot/record")
def record_snapshot(question_id: int, payload: dict, db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Question not found")
    detections = payload.get("detections", [])
    if not isinstance(detections, list):
        raise HTTPException(400, "detections must be a list")

    # Group all entries under one snapshot id (max+1)
    max_snap = db.execute(
        select(func.max(Vote.snapshot_id)).where(Vote.question_id == question_id)
    ).scalar()
    snap_id = (max_snap or 0) + 1

    # Look up persons in bulk
    aruco_ids = [int(d["aruco_id"]) for d in detections if "aruco_id" in d]
    marker_rows = (
        db.execute(
            select(Marker)
            .options(joinedload(Marker.person))
            .where(Marker.aruco_id.in_(aruco_ids))
        )
        .scalars()
        .all()
    )
    marker_lookup = {m.aruco_id: m for m in marker_rows}

    seen: set[int] = set()
    written = 0
    for d in detections:
        aid = int(d.get("aruco_id"))
        if aid in seen:
            continue
        seen.add(aid)
        m = marker_lookup.get(aid)
        v = Vote(
            question_id=question_id,
            snapshot_id=snap_id,
            marker_aruco_id=aid,
            zone_id=d.get("zone_id"),
            zone_label=d.get("zone_label"),
            person_id=m.person_id if m else None,
            person_name=m.person.name if (m and m.person) else None,
        )
        db.add(v)
        written += 1
    db.commit()
    return {"snapshot_id": snap_id, "votes": written}


@app.get("/api/questions/{question_id}/votes", response_model=list[VoteOut])
def list_votes(question_id: int, db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(Vote)
            .where(Vote.question_id == question_id)
            .order_by(Vote.snapshot_id.desc(), Vote.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        VoteOut(
            id=v.id,
            question_id=v.question_id,
            snapshot_id=v.snapshot_id,
            marker_aruco_id=v.marker_aruco_id,
            zone_id=v.zone_id,
            zone_label=v.zone_label,
            person_id=v.person_id,
            person_name=v.person_name,
            recorded_at=v.recorded_at,
        )
        for v in rows
    ]


@app.get("/api/questions/{question_id}/summary")
def question_summary(question_id: int, db: Session = Depends(get_db)):
    """Latest snapshot grouped by zone + per-person history across snapshots."""
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, "Not found")

    rows = (
        db.execute(
            select(Vote).where(Vote.question_id == question_id).order_by(Vote.snapshot_id)
        )
        .scalars()
        .all()
    )

    snapshots: dict[int, list[Vote]] = {}
    for v in rows:
        snapshots.setdefault(v.snapshot_id, []).append(v)

    latest_snap_id = max(snapshots) if snapshots else None
    latest_breakdown: dict[str, int] = {}
    if latest_snap_id is not None:
        for v in snapshots[latest_snap_id]:
            key = v.zone_label or "(unzoned)"
            latest_breakdown[key] = latest_breakdown.get(key, 0) + 1

    return {
        "question": _question_to_out(q).model_dump(),
        "snapshots": [
            {
                "snapshot_id": sid,
                "recorded_at": min(v.recorded_at for v in vs).isoformat(),
                "by_zone": _count_by_zone(vs),
                "entries": [
                    {
                        "aruco_id": v.marker_aruco_id,
                        "person": v.person_name,
                        "zone": v.zone_label,
                    }
                    for v in vs
                ],
            }
            for sid, vs in sorted(snapshots.items(), key=lambda kv: kv[0], reverse=True)
        ],
        "latest_breakdown": latest_breakdown,
    }


def _count_by_zone(votes: list[Vote]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in votes:
        key = v.zone_label or "(unzoned)"
        out[key] = out.get(key, 0) + 1
    return out


# ---------- tracking ----------

def _tracking_to_out(s: TrackingSession, sample_count: int = 0, markers_seen: int = 0) -> TrackingSessionOut:
    return TrackingSessionOut(
        id=s.id, name=s.name,
        proximity_norm=s.proximity_norm,
        sample_interval_ms=s.sample_interval_ms,
        started_at=s.started_at, stopped_at=s.stopped_at,
        sample_count=sample_count, markers_seen=markers_seen,
    )


def _tracking_session_stats(db: Session, session_id: int) -> tuple[int, int]:
    sample_count = db.execute(
        select(func.count(TrackingSample.id)).where(TrackingSample.session_id == session_id)
    ).scalar() or 0
    markers_seen = db.execute(
        select(func.count(func.distinct(TrackingSample.marker_aruco_id)))
        .where(TrackingSample.session_id == session_id)
    ).scalar() or 0
    return int(sample_count), int(markers_seen)


@app.get("/api/tracking/sessions", response_model=list[TrackingSessionOut])
def list_tracking_sessions(db: Session = Depends(get_db)):
    rows = db.execute(
        select(TrackingSession).order_by(TrackingSession.started_at.desc())
    ).scalars().all()
    out: list[TrackingSessionOut] = []
    for s in rows:
        sc, ms = _tracking_session_stats(db, s.id)
        out.append(_tracking_to_out(s, sc, ms))
    return out


@app.get("/api/tracking/sessions/active", response_model=Optional[TrackingSessionOut])
def get_active_tracking(db: Session = Depends(get_db)):
    s = db.execute(
        select(TrackingSession).where(TrackingSession.stopped_at.is_(None))
        .order_by(TrackingSession.started_at.desc())
    ).scalars().first()
    if not s:
        return None
    sc, ms = _tracking_session_stats(db, s.id)
    return _tracking_to_out(s, sc, ms)


@app.post("/api/tracking/sessions", response_model=TrackingSessionOut)
def start_tracking(payload: TrackingSessionIn, db: Session = Depends(get_db)):
    # Stop any other active session first — only one at a time.
    db.query(TrackingSession).filter(TrackingSession.stopped_at.is_(None)).update(
        {TrackingSession.stopped_at: datetime.utcnow()}, synchronize_session=False
    )
    s = TrackingSession(
        name=payload.name.strip() or f"Session {datetime.utcnow().isoformat(timespec='seconds')}",
        proximity_norm=max(0.01, min(payload.proximity_norm, 1.0)),
        sample_interval_ms=max(100, min(payload.sample_interval_ms, 10000)),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _tracking_to_out(s)


@app.put("/api/tracking/sessions/{session_id}/stop", response_model=TrackingSessionOut)
def stop_tracking(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrackingSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    if s.stopped_at is None:
        s.stopped_at = datetime.utcnow()
        db.commit()
        db.refresh(s)
    sc, ms = _tracking_session_stats(db, s.id)
    return _tracking_to_out(s, sc, ms)


@app.delete("/api/tracking/sessions/{session_id}")
def delete_tracking(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrackingSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


@app.get("/api/tracking/sessions/{session_id}/timeline")
def tracking_timeline(
    session_id: int,
    bucket_ms: int = 500,
    db: Session = Depends(get_db),
):
    """Streamable NDJSON of per-bucket position snapshots — used by the
    /track report panel scrubber. One JSON object per bucket:

      {"t": "2026-05-01T15:32:11.500Z",
       "frame": [{"id": 47, "x": 0.31, "y": 0.62, "name": "Anna"}, ...]}

    Buckets are clipped to the session's actual time span; sub-millisecond
    intervals are coalesced to a single bucket.
    """
    s = db.get(TrackingSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    bucket_ms = max(50, min(bucket_ms, 60000))

    rows = (
        db.execute(
            select(TrackingSample)
            .where(TrackingSample.session_id == session_id)
            .order_by(TrackingSample.t.asc(), TrackingSample.id.asc())
        )
        .scalars().all()
    )

    # Lookup person names for IDs we'll surface.
    seen_ids = {r.marker_aruco_id for r in rows}
    names: dict[int, str] = {}
    if seen_ids:
        for m in (
            db.execute(
                select(Marker).options(joinedload(Marker.person))
                .where(Marker.aruco_id.in_(seen_ids))
            ).scalars().all()
        ):
            if m.person:
                names[m.aruco_id] = m.person.name

    started_at = s.started_at

    def _bucket_index(t: datetime) -> int:
        return int((t - started_at).total_seconds() * 1000.0 // bucket_ms)

    def _stream():
        if not rows:
            return
        current_bucket: Optional[int] = None
        frame: list[dict] = []
        # First-write-wins per (bucket, marker) so a marker doesn't appear
        # twice in the same bucket if multiple samples landed.
        seen_in_bucket: set[int] = set()
        for r in rows:
            b = _bucket_index(r.t)
            if current_bucket is None:
                current_bucket = b
            if b != current_bucket:
                yield json.dumps({
                    "t_ms": current_bucket * bucket_ms,
                    "frame": frame,
                }) + "\n"
                current_bucket = b
                frame = []
                seen_in_bucket = set()
            if r.marker_aruco_id in seen_in_bucket:
                continue
            seen_in_bucket.add(r.marker_aruco_id)
            entry = {
                "id": r.marker_aruco_id,
                "x": round(r.x_norm, 4),
                "y": round(r.y_norm, 4),
            }
            if r.world_x_m is not None:
                entry["wx_m"] = round(r.world_x_m, 3)
                entry["wy_m"] = round(r.world_y_m, 3)
            n = names.get(r.marker_aruco_id)
            if n:
                entry["name"] = n
            frame.append(entry)
        if frame:
            yield json.dumps({
                "t_ms": (current_bucket or 0) * bucket_ms,
                "frame": frame,
            }) + "\n"

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson",
        headers={
            "X-Bucket-Ms": str(bucket_ms),
            "X-Started-At": started_at.isoformat(),
        },
    )


@app.get("/api/tracking/sessions/{session_id}/report")
def tracking_report(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrackingSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    _t0 = time.monotonic()
    report = tracking_mod.compute_report(db, s)
    obs.record_metric(
        "db.report_compute_ms",
        int((time.monotonic() - _t0) * 1000),
        session_id=session_id,
        sample_count=report.get("sample_count", 0),
    )
    sc, ms = _tracking_session_stats(db, s.id)
    return {
        "session": _tracking_to_out(s, sc, ms).model_dump(),
        **report,
    }


# Per-process throttle: only one DB write per session per sample_interval,
# even if multiple WS clients are streaming frames simultaneously. Each
# entry holds the monotonic time of the last write for that session id.
_last_tracking_write: dict[int, float] = {}


def _record_tracking_samples(
    session_id: int,
    sample_interval_ms: int,
    detections_payload: list[dict],
    now_monotonic: float,
) -> int:
    """Returns the number of rows written this turn (0 if throttled or empty)."""
    last = _last_tracking_write.get(session_id, 0.0)
    if (now_monotonic - last) * 1000.0 < sample_interval_ms:
        return 0
    _last_tracking_write[session_id] = now_monotonic
    if not detections_payload:
        return 0
    from .db import SessionLocal
    db = SessionLocal()
    try:
        ts = datetime.utcnow()
        rows: list[TrackingSample] = []
        for d in detections_payload:
            p = d.get("pose")  # ADR 0048 — present iff intrinsic + extrinsic done
            xyz = (p or {}).get("world_xyz_m")
            rows.append(
                TrackingSample(
                    session_id=session_id, t=ts,
                    marker_aruco_id=d["aruco_id"],
                    x_norm=float(d["center_norm"][0]),
                    y_norm=float(d["center_norm"][1]),
                    world_x_m=float(xyz[0]) if xyz else None,
                    world_y_m=float(xyz[1]) if xyz else None,
                    world_z_m=float(xyz[2]) if xyz else None,
                    yaw_deg=  float(p["yaw_deg"])   if p else None,
                    pitch_deg=float(p["pitch_deg"]) if p else None,
                    roll_deg= float(p["roll_deg"])  if p else None,
                    reproj_error_px=float(p["reproj_error_px"]) if p else None,
                )
            )
        db.bulk_save_objects(rows)
        db.commit()
        return len(rows)
    finally:
        db.close()


def _load_active_tracking() -> Optional[dict]:
    from .db import SessionLocal
    db = SessionLocal()
    try:
        s = db.execute(
            select(TrackingSession).where(TrackingSession.stopped_at.is_(None))
            .order_by(TrackingSession.started_at.desc())
        ).scalars().first()
        if not s:
            return None
        return {
            "id": s.id, "name": s.name,
            "proximity_norm": s.proximity_norm,
            "sample_interval_ms": s.sample_interval_ms,
            "started_at": s.started_at.isoformat(),
        }
    finally:
        db.close()


# ---------- broadcast to /present and other passive viewers ----------
#
# /ws/detect is per-client: each browser sending frames gets its own results
# back. /present (and similar audience-facing pages) need the latest detection
# state without owning a camera. The WS handler pushes each result to a list
# of observers; subscribers connect via /ws/observe and just receive.

_observers: list["WebSocket"] = []


async def _broadcast_to_observers(payload: dict) -> None:
    """Best-effort broadcast — drop dead sockets silently."""
    if not _observers:
        return
    dead: list[WebSocket] = []
    for ws in _observers:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _observers.remove(ws)
        except ValueError:
            pass


@app.websocket("/ws/observe")
async def ws_observe(ws: WebSocket):
    """Read-only stream of the latest detection state. Sends an immediate
    'hello' with the current active question + zones so the page renders
    something even if no camera is running yet."""
    await ws.accept()
    _observers.append(ws)
    try:
        # Immediate hello so /present can render before the next live frame.
        active = _load_active_question()
        formation = active.get("formation") if active else None
        zones = _load_zones_dict(formation=formation)
        await ws.send_json({
            "ok": True,
            "kind": "hello",
            "active_question": active,
            "zones": zones,
            "zone_counts": {z["id"]: 0 for z in zones},
            "detections": [],
        })
        while True:
            # Keep the connection alive; observer doesn't send anything meaningful.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            _observers.remove(ws)
        except ValueError:
            pass


# ---------- live detection websocket ----------

@app.websocket("/ws/detect")
async def ws_detect(ws: WebSocket):
    await ws.accept()
    last_state_reload = 0.0
    cached_zones: list[dict] = []
    cached_active: Optional[dict] = None
    cached_tracking: Optional[dict] = None
    cached_camera: Optional[dict] = None  # ADR 0048 — intrinsic/extrinsic + marker meta

    # Bandwidth tracking — sum bytes per 1s window, emit metric per window.
    bw_window_start = time.time()
    bw_bytes_in_window = 0

    # ADR 0004 — per-connection marker tracker for EMA smoothing + alive-window.
    marker_tracker = tracker_mod.MarkerTracker()

    # ADR 0015 — anchor drift monitor. Wakes up once the camera is calibrated
    # and we know the anchor baseline + corner ids.
    drift_monitor = drift_mod.AnchorDriftMonitor()
    drift_configured = False

    try:
        while True:
            data = await ws.receive_bytes()
            now = time.time()
            bw_bytes_in_window += len(data)
            if now - bw_window_start >= 1.0:
                obs.record_metric(
                    "ws.bandwidth_mbps",
                    round(bw_bytes_in_window * 8 / 1_000_000.0 / (now - bw_window_start), 3),
                )
                bw_window_start = now
                bw_bytes_in_window = 0
            if now - last_state_reload > 1.0:
                cached_active = _load_active_question()
                active_formation = cached_active.get("formation") if cached_active else None
                cached_zones = _load_zones_dict(formation=active_formation)
                cached_tracking = _load_active_tracking()
                cached_camera = _load_active_camera()
                last_state_reload = now

            arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                await ws.send_json({"ok": False, "error": "decode failed"})
                continue

            h, w = frame.shape[:2]
            _detect_t0 = time.monotonic()
            results = detection.detect(frame)
            _detect_ms = int((time.monotonic() - _detect_t0) * 1000)
            obs.record_metric("detection.latency_ms", _detect_ms,
                              resolution=f"{w}x{h}")
            obs.record_metric("detection.markers_seen", len(results))

            # Split detections into person vs control.
            person_results = [d for d in results if not control_mod.is_control_id(d.aruco_id)]
            control_ids = {d.aruco_id for d in results if control_mod.is_control_id(d.aruco_id)}

            # Run the command router; fire actions for any cards held still long enough.
            fired_now = control_mod.router.update(control_ids, now)
            control_events: list[dict] = []
            for mid in fired_now:
                ev = control_mod.fire(mid)
                if ev:
                    control_events.append({
                        "aruco_id": ev.aruco_id, "action": ev.action,
                        "label": ev.label, "t": ev.t,
                    })
            # If any actions fired, force a state reload on the next frame so
            # downstream state (active question, active tracking, zones for
            # the new question's formation) refreshes immediately.
            if fired_now:
                last_state_reload = 0.0

            zones_norm = [
                {"id": z["id"], "label": z["label"], "polygon": z["polygon"]}
                for z in cached_zones
            ]

            zone_counts: dict[int, int] = {z["id"]: 0 for z in cached_zones}
            zone_label_lookup = {z["id"]: z["label"] for z in cached_zones}

            marker_meta = _marker_meta_for(set(d.aruco_id for d in person_results))

            # ADR 0048 — pose estimation when intrinsics are calibrated.
            # Only run on person_results; control markers don't need 3D pose.
            poses: dict[int, detection.PoseDetection] = {}
            if cached_camera and cached_camera.get("K") is not None:
                poses = detection.estimate_pose(
                    person_results,
                    np.array(cached_camera["K"], dtype=np.float64),
                    np.array(cached_camera["dist"], dtype=np.float64),
                    cached_camera["marker_size_m"],
                )

            # ADR 0050 — single-camera scene reconstruction.
            scene_payload: Optional[dict] = None
            extrinsic: Optional[pose_mod.Extrinsic] = None
            if cached_camera and cached_camera.get("R") is not None and poses:
                extrinsic = pose_mod.Extrinsic(
                    R=np.array(cached_camera["R"], dtype=np.float64),
                    t=np.array(cached_camera["t"], dtype=np.float64),
                )
                marker_obs = scene_mod.build_marker_observations(
                    person_results, poses, extrinsic, marker_meta
                )
                people = scene_mod.fuse_person_observations(marker_obs)
                scene_payload = {
                    "world_frame": {
                        "floor_w_m": cached_camera["floor_w_m"],
                        "floor_h_m": cached_camera["floor_h_m"],
                        "camera_position_world_m": cached_camera.get("camera_pos_world"),
                    },
                    "markers": [scene_mod.serialize_marker(m) for m in marker_obs],
                    "people":  [scene_mod.serialize_person(p) for p in people],
                    "coverage_pct": (
                        round(100.0 * len(poses) / max(1, len(person_results)), 1)
                    ),
                }

            detections_payload = []
            corner_centers_px: dict[str, list[float]] = {}
            corner_ids = (cached_camera or {}).get("corner_ids") or {}
            corner_lookup = {int(v): k for k, v in corner_ids.items()}
            # Corner-marker pixel positions: scan ALL detections (corner markers may
            # live anywhere in the dictionary, including the control range).
            for d in results:
                if d.aruco_id in corner_lookup:
                    corner_centers_px[corner_lookup[d.aruco_id]] = list(d.center)
            for d in person_results:
                cx, cy = d.center
                center_norm = (cx / w, cy / h)
                zid = detection.assign_zone(center_norm, zones_norm)
                if zid is not None:
                    zone_counts[zid] = zone_counts.get(zid, 0) + 1
                # corner_centers_px was populated above by the all-detections scan.

                entry = {
                    "aruco_id": d.aruco_id,
                    "corners_norm": [[c[0] / w, c[1] / h] for c in d.corners],
                    "center_norm": [center_norm[0], center_norm[1]],
                    "zone_id": zid,
                    "zone_label": zone_label_lookup.get(zid),
                    "person_name": marker_meta.get(d.aruco_id, {}).get("person_name"),
                    "placement": marker_meta.get(d.aruco_id, {}).get("placement", "hat"),
                }
                p = poses.get(d.aruco_id)
                if p is not None and extrinsic is not None:
                    xyz_w, R_w = pose_mod.marker_pose_world(p.rvec, p.tvec, extrinsic)
                    yaw, pitch, roll = pose_mod.R_to_euler_zyx_deg(R_w)
                    entry["pose"] = {
                        "world_xyz_m": [float(xyz_w[0]), float(xyz_w[1]), float(xyz_w[2])],
                        "yaw_deg": round(yaw, 2),
                        "pitch_deg": round(pitch, 2),
                        "roll_deg": round(roll, 2),
                        "reproj_error_px": round(p.reproj_error_px, 3),
                    }
                elif p is not None:
                    # Intrinsic-only: report camera-frame translation so the UI
                    # can still show "z ≈ 1.2 m" depth without world frame.
                    entry["pose_camera"] = {
                        "tvec_camera_m": [float(p.tvec[0]), float(p.tvec[1]), float(p.tvec[2])],
                        "reproj_error_px": round(p.reproj_error_px, 3),
                    }
                detections_payload.append(entry)

            # ADR 0004 — apply EMA smoothing + alive-window. Patches center_norm
            # in place and appends ghost entries for markers that briefly
            # missed detection. Must run BEFORE tracking samples so ghosts
            # contribute (continuity over a 1 s blip) and BEFORE the WS payload.
            detections_payload, ghost_count = marker_tracker.update_with_detections(
                detections_payload, now,
            )
            if ghost_count:
                obs.record_metric("detection.ghosts", ghost_count)

            # Tracking: drop a sample row per visible marker, throttled per session.
            if cached_tracking:
                wrote = _record_tracking_samples(
                    cached_tracking["id"],
                    cached_tracking["sample_interval_ms"],
                    detections_payload,
                    now,
                )
                if wrote:
                    obs.record_metric(
                        "tracking.sample_writes",
                        wrote,
                        session_id=cached_tracking["id"],
                    )

            calibration_hint: Optional[dict] = None
            if cached_camera and corner_centers_px:
                calibration_hint = {
                    "camera_id": cached_camera["id"],
                    "corners_visible_px": corner_centers_px,
                    "all_four_visible": len(corner_centers_px) == 4,
                    "floor_w_m": cached_camera["floor_w_m"],
                    "floor_h_m": cached_camera["floor_h_m"],
                }

            # ADR 0015 — anchor drift detection. Once the camera has stored
            # corner-pixel baselines (saved at extrinsic-calibration time),
            # configure the monitor and tick it each frame.
            drift_events: list[dict] = []
            baseline_px = (cached_camera or {}).get("anchor_baseline_px")
            if cached_camera and baseline_px and corner_ids:
                if not drift_configured:
                    drift_monitor.configure(
                        baseline_corners_px={k: tuple(v) for k, v in baseline_px.items()},
                        corner_ids={k: int(v) for k, v in corner_ids.items()},
                        frame_size_px=(w, h),
                    )
                    drift_configured = True
                events = drift_monitor.update(corner_centers_px, now)
                for ev in events:
                    drift_events.append({
                        "kind": ev.kind, "severity": ev.severity,
                        "message": ev.message, "details": ev.details,
                    })
                    obs.record_metric(
                        f"drift.{ev.kind}", 1,
                        anchor=ev.details.get("anchor"),
                    )

            payload = {
                "ok": True,
                "frame_w": w,
                "frame_h": h,
                "active_question": cached_active,
                "active_tracking": cached_tracking,
                "zones": cached_zones,
                "detections": detections_payload,
                "zone_counts": zone_counts,
                "camera": {
                    "id": cached_camera["id"],
                    "intrinsic_calibrated": cached_camera.get("K") is not None,
                    "extrinsic_calibrated": cached_camera.get("R") is not None,
                } if cached_camera else None,
                "scene_world": scene_payload,
                "calibration_hint": calibration_hint,
                "control_events": control_events,
                "drift_events": drift_events,
            }
            await ws.send_json(payload)
            # Mirror to /present and any other observers.
            await _broadcast_to_observers(payload)
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        try:
            await ws.send_json({"ok": False, "error": str(e)})
        except Exception:
            pass


def _load_zones_dict(formation: Optional[str] = None) -> list[dict]:
    """Zones currently in scope for the live overlay.

    If `formation` is set, only zones tagged with that formation are returned —
    this is what makes the overlay swap automatically when the active question
    changes from `line` to `matrix_2x2` etc.

    If no formation is requested, fall back to: zones whose formation is null
    (manually-drawn legacy zones). This keeps the live page useful when no
    question is active without dumping every formation's zones at once.
    """
    from .db import SessionLocal
    db = SessionLocal()
    try:
        if formation:
            rows = db.execute(
                select(Zone).where(Zone.formation == formation).order_by(Zone.id)
            ).scalars().all()
        else:
            rows = db.execute(
                select(Zone).where(Zone.formation.is_(None)).order_by(Zone.id)
            ).scalars().all()
        return [
            {
                "id": z.id,
                "name": z.name,
                "label": z.label,
                "color": z.color,
                "polygon": z.points(),
                "formation": z.formation,
            }
            for z in rows
        ]
    finally:
        db.close()


def _load_active_question() -> Optional[dict]:
    from .db import SessionLocal
    db = SessionLocal()
    try:
        q = db.execute(select(Question).where(Question.is_active == 1)).scalars().first()
        if not q:
            return None
        return {
            "id": q.id,
            "text": q.text,
            "block": q.block,
            "formation": q.formation,
            "position": q.position or 0,
        }
    finally:
        db.close()


def _person_map_for(aruco_ids: set[int]) -> dict[int, str]:
    if not aruco_ids:
        return {}
    from .db import SessionLocal
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(Marker)
                .options(joinedload(Marker.person))
                .where(Marker.aruco_id.in_(aruco_ids))
            )
            .scalars()
            .all()
        )
        return {m.aruco_id: (m.person.name if m.person else None) for m in rows}
    finally:
        db.close()


def _marker_meta_for(aruco_ids: set[int]) -> dict[int, dict]:
    """Bulk lookup of person_id / person_name / placement for a frame's markers."""
    if not aruco_ids:
        return {}
    from .db import SessionLocal
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(Marker)
                .options(joinedload(Marker.person))
                .where(Marker.aruco_id.in_(aruco_ids))
            )
            .scalars()
            .all()
        )
        return {
            m.aruco_id: {
                "person_id": m.person_id,
                "person_name": m.person.name if m.person else None,
                "placement": m.placement or "hat",
            }
            for m in rows
        }
    finally:
        db.close()


def _load_active_camera() -> Optional[dict]:
    """The current single-camera deployment uses id=1.  Returns None if missing."""
    from .db import SessionLocal
    db = SessionLocal()
    try:
        c = db.get(Camera, 1)
        if c is None:
            return None
        cam_pos: Optional[list[float]] = None
        if c.has_extrinsic():
            try:
                ext = pose_mod.Extrinsic(
                    R=np.array(c.R(), dtype=np.float64),
                    t=np.array(c.t(), dtype=np.float64),
                )
                cam_pos = ext.camera_position_world().tolist()
            except Exception:
                cam_pos = None
        baseline = None
        if c.anchor_baseline_px_json:
            try:
                baseline = json.loads(c.anchor_baseline_px_json)
            except Exception:
                baseline = None
        return {
            "id": c.id,
            "name": c.name,
            "marker_size_m": c.marker_size_m,
            "K":    c.K(),
            "dist": c.dist(),
            "R":    c.R(),
            "t":    c.t(),
            "floor_w_m": c.floor_rect_w_m,
            "floor_h_m": c.floor_rect_h_m,
            "corner_ids": c.corner_ids() or {},
            "camera_pos_world": cam_pos,
            "anchor_baseline_px": baseline,
        }
    finally:
        db.close()


# ---------- frontend ----------

app.mount("/static", StaticFiles(directory=str(FRONTEND / "static")), name="static")


@app.get("/")
def root():
    return FileResponse(str(FRONTEND / "index.html"))


@app.get("/admin")
def admin():
    return FileResponse(str(FRONTEND / "admin.html"))


@app.get("/track")
def track_page():
    return FileResponse(str(FRONTEND / "track.html"))


# ---------- auth (ADR 0001) ----------

@app.get("/login")
def login_get(next: str = "/admin"):
    return auth_mod.login_page(next_path=next)


@app.post("/login")
async def login_post(request: Request):
    form = await request.form()
    token = (form.get("token") or "").strip()
    next_path = (form.get("next") or "/admin").strip() or "/admin"
    expected = auth_mod.app_token()
    if not expected:
        # Auth is disabled — the form was a no-op. Redirect to next.
        return RedirectResponse(next_path, status_code=303)
    import hmac
    if not hmac.compare_digest(token, expected):
        return auth_mod.login_page(error="Invalid token", next_path=next_path)
    response = RedirectResponse(next_path, status_code=303)
    auth_mod.login_set_cookie(response, token)
    return response


@app.post("/logout")
def logout_post():
    response = RedirectResponse("/login", status_code=303)
    auth_mod.logout(response)
    return response


@app.get("/track3d")
def track3d_page():
    """ADR 0050 — 3D world-frame viewer of the live scene."""
    return FileResponse(str(FRONTEND / "track3d.html"))


@app.get("/present")
def present_page():
    return FileResponse(str(FRONTEND / "present.html"))


@app.get("/charuco")
def charuco_page():
    """Fullscreen ChArUco board for tablet display during intrinsic calibration."""
    return FileResponse(str(FRONTEND / "charuco.html"))


@app.get("/m/{aruco_id}")
def marker_phone_page(aruco_id: int, db: Session = Depends(get_db)):
    """Fullscreen marker display optimised for phones."""
    if not db.get(Marker, aruco_id):
        raise HTTPException(404, "Marker not found")
    return FileResponse(str(FRONTEND / "marker.html"))


@app.get("/api/qr")
def share_qr(text: str = Query(..., min_length=1, max_length=500), size: int = 6):
    """Generate a QR code PNG that encodes the given text/URL — used for the 'share to phone' modal."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=max(2, min(size, 20)),
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/system/lan")
def lan_ips():
    """Best-effort local IPs of the *host* the container is talking to.

    Inside Docker we see container-local IPs which aren't useful for phones.
    The frontend should prefer `location.host` if it's already an IP; this
    endpoint returns a hint only.
    """
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return {"ips": ips}
