import json
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    markers: Mapped[list["Marker"]] = relationship(back_populates="person", cascade="all,delete-orphan")


class Marker(Base):
    __tablename__ = "markers"
    aruco_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dictionary: Mapped[str] = mapped_column(String(50), nullable=False)
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    # ADR 0049 — body placement: 'hat' | 'chest' | 'back' | 'wrist' | 'accessory'.
    # Default 'hat' matches the implicit single-marker assumption of the pre-0049 system.
    placement: Mapped[str] = mapped_column(String(20), default="hat", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Optional["Person"]] = relationship(back_populates="markers")


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#22c55e")
    polygon: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of [x,y] in 0..1
    formation: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    locked: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def points(self) -> list[list[float]]:
        return json.loads(self.polygon)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=0)  # 0/1
    block: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    formation: Mapped[Optional[str]] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Vote(Base):
    """A snapshot of a single marker's location for a given question."""
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, index=True)  # group rows of one snapshot
    marker_aruco_id: Mapped[int] = mapped_column(Integer, nullable=False)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"))
    zone_label: Mapped[Optional[str]] = mapped_column(String(100))
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    person_name: Mapped[Optional[str]] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("snapshot_id", "marker_aruco_id", name="uq_snapshot_marker"),
    )


class Metric(Base):
    """ADR 0036 — system-self telemetry. Append-only (name, value, tags) series.

    Hot-path callers batch these via record_metric() in main.py.
    """
    __tablename__ = "metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float] = mapped_column(Float)
    tags_json: Mapped[Optional[str]] = mapped_column(Text)


class AuditLog(Base):
    """ADR 0009 — one row per successful state-mutating request to /api/*.

    Captures who (token-hash), what (method + path), when, and a small
    redacted body summary so post-incident review can answer 'who deleted
    question 17 during the workshop?'.
    """
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    actor_token_hash: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(400), index=True)
    query: Mapped[Optional[str]] = mapped_column(String(800))
    status_code: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[Optional[str]] = mapped_column(String(36))
    body_summary: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class ControlMarker(Base):
    """Control markers — IDs reserved at the top of the dictionary that fire
    actions instead of representing people. Implements ADR 0011 + ADR 0014."""
    __tablename__ = "control_markers"
    aruco_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrackingSession(Base):
    """A 'who-was-where, with whom, for how long' recording window.

    While a session has stopped_at = NULL, the WS detection loop records one
    TrackingSample per visible marker every `sample_interval_ms` milliseconds.
    Reports are computed on demand from raw positions so the proximity
    threshold can be tuned after the fact.
    """
    __tablename__ = "tracking_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    proximity_norm: Mapped[float] = mapped_column(Float, default=0.12)
    sample_interval_ms: Mapped[int] = mapped_column(Integer, default=500)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class TrackingSample(Base):
    __tablename__ = "tracking_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("tracking_sessions.id", ondelete="CASCADE"), index=True
    )
    t: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    marker_aruco_id: Mapped[int] = mapped_column(Integer)
    x_norm: Mapped[float] = mapped_column(Float)
    y_norm: Mapped[float] = mapped_column(Float)
    # ADR 0048 — world-frame pose, populated when the active camera is fully
    # calibrated (intrinsic + extrinsic). NULL otherwise so historical reports
    # written before calibration still load cleanly.
    world_x_m: Mapped[Optional[float]] = mapped_column(Float)
    world_y_m: Mapped[Optional[float]] = mapped_column(Float)
    world_z_m: Mapped[Optional[float]] = mapped_column(Float)
    yaw_deg:   Mapped[Optional[float]] = mapped_column(Float)
    pitch_deg: Mapped[Optional[float]] = mapped_column(Float)
    roll_deg:  Mapped[Optional[float]] = mapped_column(Float)
    reproj_error_px: Mapped[Optional[float]] = mapped_column(Float)

    __table_args__ = (
        Index("ix_tracking_samples_session_t", "session_id", "t"),
    )


class Camera(Base):
    """Per-camera intrinsic + extrinsic calibration (ADR 0003 + 0012 + 0048).

    A single-laptop deployment has exactly one row, id=1, name='default'.
    Multi-camera deployments (ADR 0005 / 0050) add one row per upload source.

    Intrinsic: K, dist, marker_size_m — needed by `cv2.aruco.estimatePoseSingleMarkers`.
    Extrinsic: R, t in world frame — needed to lift camera-frame pose into
    the shared room frame so multiple cameras agree on `(x, y, z)`.
    """
    __tablename__ = "cameras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="default")

    # Intrinsic (ADR 0048).
    K_json: Mapped[Optional[str]] = mapped_column(Text)            # 3x3 list-of-lists
    dist_json: Mapped[Optional[str]] = mapped_column(Text)         # 1xN list
    marker_size_m: Mapped[float] = mapped_column(Float, default=0.15, nullable=False)
    intrinsic_calibrated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    intrinsic_reproj_error_px: Mapped[Optional[float]] = mapped_column(Float)
    intrinsic_image_w: Mapped[Optional[int]] = mapped_column(Integer)
    intrinsic_image_h: Mapped[Optional[int]] = mapped_column(Integer)

    # Extrinsic (ADR 0012). World frame is X-right, Y-forward (along the
    # known floor rectangle), Z-up.
    extrinsic_R_json: Mapped[Optional[str]] = mapped_column(Text)  # 3x3 rotation, world->camera
    extrinsic_t_json: Mapped[Optional[str]] = mapped_column(Text)  # 3-vec translation, world->camera
    extrinsic_calibrated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    extrinsic_reproj_error_px: Mapped[Optional[float]] = mapped_column(Float)
    # ADR 0015 — image-pixel positions of the four anchors at calibration
    # time. JSON {"tl": [px, py], "tr": [px, py], ...}. Drift detector
    # compares live anchor centres to this baseline.
    anchor_baseline_px_json: Mapped[Optional[str]] = mapped_column(Text)

    # The four-corner floor rectangle (ADR 0012).
    floor_rect_w_m: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    floor_rect_h_m: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    # JSON {"tl": id, "tr": id, "br": id, "bl": id}. Defaults are computed
    # at first-run from the active dictionary's top four reserved ids.
    corner_ids_json: Mapped[Optional[str]] = mapped_column(Text)

    # ADR 0050+ — RTSP / IP camera URL. When set, a backend worker spawns on
    # startup (and on update), pulls frames via OpenCV, and publishes to the
    # SceneAggregator just like a browser /ws/detect client does.
    rtsp_url: Mapped[Optional[str]] = mapped_column(String(500))
    rtsp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def K(self) -> Optional[list[list[float]]]:
        return json.loads(self.K_json) if self.K_json else None

    def dist(self) -> Optional[list[float]]:
        return json.loads(self.dist_json) if self.dist_json else None

    def R(self) -> Optional[list[list[float]]]:
        return json.loads(self.extrinsic_R_json) if self.extrinsic_R_json else None

    def t(self) -> Optional[list[float]]:
        return json.loads(self.extrinsic_t_json) if self.extrinsic_t_json else None

    def corner_ids(self) -> Optional[dict]:
        return json.loads(self.corner_ids_json) if self.corner_ids_json else None

    def has_intrinsic(self) -> bool:
        return self.K_json is not None and self.dist_json is not None

    def has_extrinsic(self) -> bool:
        return self.extrinsic_R_json is not None and self.extrinsic_t_json is not None


class SceneRecording(Base):
    """A recorded run of fused world-frame scenes.

    Frames are written to JSONL at `{DATA_DIR}/recordings/{id}.jsonl`; one
    line per fused scene, each with `rel_t` (seconds since recording start)
    and the full `scene_world` payload that was sent to /ws/scene observers.
    Replay just streams the file at original timing.
    """
    __tablename__ = "scene_recordings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    frame_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


def init_db() -> None:
    """Run Alembic upgrade head — replaces the previous hand-rolled migrations.

    On a fresh DB the baseline migration (0001) creates every table from
    SQLAlchemy metadata. Existing prod DBs already have the tables and a
    bootstrap step stamps them at the baseline so subsequent migrations apply
    cleanly. The legacy hand-migrations stay in place as a safety net for
    any DB that hasn't been stamped yet.
    """
    # Legacy migrations first — they're idempotent ALTER TABLE ... ADD COLUMN
    # with a column-exists check, so running them on an already-migrated DB
    # is a no-op. They cover the schema deltas before Alembic landed.
    Base.metadata.create_all(engine)
    _migrate_questions()
    _migrate_markers()
    _migrate_tracking_samples()
    _migrate_cameras()
    _seed_default_camera()
    _alembic_upgrade()


def _alembic_upgrade() -> None:
    """Run `alembic upgrade head` programmatically, with a one-shot stamp for
    pre-Alembic prod databases (so the baseline migration's create_all
    becomes a no-op)."""
    try:
        from alembic.config import Config
        from alembic import command
    except ImportError:
        # Alembic not installed (e.g. running in a slim test environment) —
        # legacy hand-migrations above already brought the schema up.
        return
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_path = os.path.join(here, "alembic.ini")
    if not os.path.exists(cfg_path):
        return
    cfg = Config(cfg_path)
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    # Detect a pre-Alembic prod DB (has tables but no alembic_version row) and
    # stamp it at baseline so upgrade head is a clean no-op.
    with engine.begin() as conn:
        has_alembic = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        has_questions = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='questions'"
        ).fetchone()
        needs_stamp = bool(has_questions) and not bool(has_alembic)
    if needs_stamp:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")


def _migrate_questions() -> None:
    """SQLite schema hand-migration for fields added after first deploy."""
    q_needed = {
        "block":     "ALTER TABLE questions ADD COLUMN block VARCHAR(200)",
        "formation": "ALTER TABLE questions ADD COLUMN formation VARCHAR(40)",
        "position":  "ALTER TABLE questions ADD COLUMN position INTEGER DEFAULT 0",
    }
    z_needed = {
        "formation": "ALTER TABLE zones ADD COLUMN formation VARCHAR(40)",
        "locked":    "ALTER TABLE zones ADD COLUMN locked INTEGER DEFAULT 0",
    }
    with engine.begin() as conn:
        q_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(questions)").all()}
        for col, ddl in q_needed.items():
            if col not in q_cols:
                conn.exec_driver_sql(ddl)
        z_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(zones)").all()}
        for col, ddl in z_needed.items():
            if col not in z_cols:
                conn.exec_driver_sql(ddl)


def _migrate_markers() -> None:
    """ADR 0049 — placement field for the multi-placement marker kit."""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(markers)").all()}
        if "placement" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE markers ADD COLUMN placement VARCHAR(20) NOT NULL DEFAULT 'hat'"
            )


def _migrate_tracking_samples() -> None:
    """ADR 0048 — world-frame pose columns on the per-frame sample row."""
    cols_to_add = {
        "world_x_m":       "ALTER TABLE tracking_samples ADD COLUMN world_x_m FLOAT",
        "world_y_m":       "ALTER TABLE tracking_samples ADD COLUMN world_y_m FLOAT",
        "world_z_m":       "ALTER TABLE tracking_samples ADD COLUMN world_z_m FLOAT",
        "yaw_deg":         "ALTER TABLE tracking_samples ADD COLUMN yaw_deg FLOAT",
        "pitch_deg":       "ALTER TABLE tracking_samples ADD COLUMN pitch_deg FLOAT",
        "roll_deg":        "ALTER TABLE tracking_samples ADD COLUMN roll_deg FLOAT",
        "reproj_error_px": "ALTER TABLE tracking_samples ADD COLUMN reproj_error_px FLOAT",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(tracking_samples)").all()}
        for col, ddl in cols_to_add.items():
            if col not in cols:
                conn.exec_driver_sql(ddl)


def _migrate_cameras() -> None:
    """RTSP ingest columns added after the baseline migration."""
    cols_to_add = {
        "rtsp_url":     "ALTER TABLE cameras ADD COLUMN rtsp_url VARCHAR(500)",
        "rtsp_enabled": "ALTER TABLE cameras ADD COLUMN rtsp_enabled BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(cameras)").all()}
        for col, ddl in cols_to_add.items():
            if col not in cols:
                conn.exec_driver_sql(ddl)


def _seed_default_camera() -> None:
    """Ensure exactly one default Camera row exists (single-camera deployments)."""
    from . import detection
    db = SessionLocal()
    try:
        existing = db.execute(
            __import__("sqlalchemy").select(Camera).where(Camera.id == 1)
        ).scalars().first()
        if existing:
            return
        # Top four ids of the active dictionary become the default corner-marker
        # reservation (ADR 0011 / 0012). With DICT_4X4_100 these are 96..99.
        dict_size = detection.dictionary_size()
        top = max(0, dict_size - 4)
        corners = {
            "tl": top + 0,
            "tr": top + 1,
            "br": top + 2,
            "bl": top + 3,
        }
        cam = Camera(
            id=1,
            name="default",
            corner_ids_json=json.dumps(corners),
        )
        db.add(cam)
        db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
