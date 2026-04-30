import io
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import qrcode
from fastapi import (
    Depends, FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from . import badges as badge_gen, detection, markers as marker_gen, tracking as tracking_mod
from .db import (
    Marker, Person, Question, TrackingSample, TrackingSession, Vote, Zone,
    get_db, init_db,
)
from .schemas import (
    MarkerAssign, MarkerCreateBatch, MarkerOut, PersonIn, PersonOut, QuestionBulkIn,
    QuestionIn, QuestionOut, TrackingSessionIn, TrackingSessionOut, VoteOut,
    ZoneIn, ZoneOut, ZonePatch,
)
from .seeds.czocha_day1 import as_records as _czocha_day1_records
from .seeds.default_zones import records_for as _default_zones_records, DEFAULTS_BY_FORMATION

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="ArUco Counter")

init_db()


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
        created_at=m.created_at,
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
    max_id = db.execute(select(func.max(Marker.aruco_id))).scalar()
    return 0 if max_id is None else max_id + 1


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
    next_id = _next_aruco_id(db)
    if next_id + payload.count > dict_size:
        remaining = max(0, dict_size - next_id)
        raise HTTPException(
            400,
            f"Dictionary {detection.get_dictionary_name()} only holds {dict_size} unique markers "
            f"(next id {next_id}, {remaining} remaining). Switch ARUCO_DICTIONARY in docker-compose.yml "
            f"to a larger one (e.g. DICT_4X4_250) and rebuild.",
        )
    created: list[Marker] = []
    for _ in range(payload.count):
        new_id = _next_aruco_id(db)
        m = Marker(
            aruco_id=new_id,
            dictionary=detection.get_dictionary_name(),
            person_id=payload.person_id,
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
    width: int = 800,
    height: int = 1000,
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


@app.get("/api/tracking/sessions/{session_id}/report")
def tracking_report(session_id: int, db: Session = Depends(get_db)):
    s = db.get(TrackingSession, session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    report = tracking_mod.compute_report(db, s)
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
) -> None:
    last = _last_tracking_write.get(session_id, 0.0)
    if (now_monotonic - last) * 1000.0 < sample_interval_ms:
        return
    _last_tracking_write[session_id] = now_monotonic
    if not detections_payload:
        return
    from .db import SessionLocal
    db = SessionLocal()
    try:
        ts = datetime.utcnow()
        rows = [
            TrackingSample(
                session_id=session_id, t=ts,
                marker_aruco_id=d["aruco_id"],
                x_norm=float(d["center_norm"][0]),
                y_norm=float(d["center_norm"][1]),
            )
            for d in detections_payload
        ]
        db.bulk_save_objects(rows)
        db.commit()
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


# ---------- live detection websocket ----------

@app.websocket("/ws/detect")
async def ws_detect(ws: WebSocket):
    await ws.accept()
    last_state_reload = 0.0
    cached_zones: list[dict] = []
    cached_active: Optional[dict] = None
    cached_tracking: Optional[dict] = None

    try:
        while True:
            data = await ws.receive_bytes()
            now = time.time()
            if now - last_state_reload > 1.0:
                cached_active = _load_active_question()
                active_formation = cached_active.get("formation") if cached_active else None
                cached_zones = _load_zones_dict(formation=active_formation)
                cached_tracking = _load_active_tracking()
                last_state_reload = now

            arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                await ws.send_json({"ok": False, "error": "decode failed"})
                continue

            h, w = frame.shape[:2]
            results = detection.detect(frame)

            zones_norm = [
                {"id": z["id"], "label": z["label"], "polygon": z["polygon"]}
                for z in cached_zones
            ]

            zone_counts: dict[int, int] = {z["id"]: 0 for z in cached_zones}
            zone_label_lookup = {z["id"]: z["label"] for z in cached_zones}

            person_map = _person_map_for(set(d.aruco_id for d in results))

            detections_payload = []
            for d in results:
                cx, cy = d.center
                center_norm = (cx / w, cy / h)
                zid = detection.assign_zone(center_norm, zones_norm)
                if zid is not None:
                    zone_counts[zid] = zone_counts.get(zid, 0) + 1
                detections_payload.append(
                    {
                        "aruco_id": d.aruco_id,
                        "corners_norm": [[c[0] / w, c[1] / h] for c in d.corners],
                        "center_norm": [center_norm[0], center_norm[1]],
                        "zone_id": zid,
                        "zone_label": zone_label_lookup.get(zid),
                        "person_name": person_map.get(d.aruco_id),
                    }
                )

            # Tracking: drop a sample row per visible marker, throttled per session.
            if cached_tracking:
                _record_tracking_samples(
                    cached_tracking["id"],
                    cached_tracking["sample_interval_ms"],
                    detections_payload,
                    now,
                )

            await ws.send_json(
                {
                    "ok": True,
                    "frame_w": w,
                    "frame_h": h,
                    "active_question": cached_active,
                    "active_tracking": cached_tracking,
                    "zones": cached_zones,
                    "detections": detections_payload,
                    "zone_counts": zone_counts,
                }
            )
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
