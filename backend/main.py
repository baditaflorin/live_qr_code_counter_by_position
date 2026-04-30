import io
import json
import os
import socket
import time
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

from . import detection, markers as marker_gen
from .db import (
    Marker, Person, Question, Vote, Zone, get_db, init_db,
)
from .schemas import (
    MarkerAssign, MarkerCreateBatch, MarkerOut, PersonIn, PersonOut, QuestionIn,
    QuestionOut, VoteOut, ZoneIn, ZoneOut,
)

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
        created_at=z.created_at,
    )


def _question_to_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        text=q.text,
        is_active=bool(q.is_active),
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
def list_zones(db: Session = Depends(get_db)):
    rows = db.execute(select(Zone).order_by(Zone.id)).scalars().all()
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
    if len(payload.polygon) < 3:
        raise HTTPException(400, "Polygon needs at least 3 points")
    z.name = payload.name.strip() or "Zone"
    z.label = payload.label.strip()
    z.color = payload.color
    z.polygon = json.dumps(payload.polygon)
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


# ---------- questions / votes ----------

@app.get("/api/questions", response_model=list[QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    rows = db.execute(select(Question).order_by(Question.created_at.desc())).scalars().all()
    return [_question_to_out(q) for q in rows]


@app.post("/api/questions", response_model=QuestionOut)
def create_question(payload: QuestionIn, db: Session = Depends(get_db)):
    q = Question(text=payload.text.strip())
    if not q.text:
        raise HTTPException(400, "Text required")
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_to_out(q)


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


# ---------- live detection websocket ----------

@app.websocket("/ws/detect")
async def ws_detect(ws: WebSocket):
    await ws.accept()
    last_zone_reload = 0.0
    cached_zones: list[dict] = []

    try:
        while True:
            data = await ws.receive_bytes()
            now = time.time()
            if now - last_zone_reload > 1.0:
                cached_zones = _load_zones_dict()
                last_zone_reload = now

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

            # Look up person names for currently-visible markers (cheap; in-memory cache)
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

            await ws.send_json(
                {
                    "ok": True,
                    "frame_w": w,
                    "frame_h": h,
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


def _load_zones_dict() -> list[dict]:
    from .db import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(select(Zone).order_by(Zone.id)).scalars().all()
        return [
            {
                "id": z.id,
                "name": z.name,
                "label": z.label,
                "color": z.color,
                "polygon": z.points(),
            }
            for z in rows
        ]
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
