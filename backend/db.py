import json
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
    create_engine,
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

    __table_args__ = (
        Index("ix_tracking_samples_session_t", "session_id", "t"),
    )


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_questions()


def _migrate_questions() -> None:
    """SQLite schema hand-migration for fields added after first deploy.

    Avoids a hard dependency on Alembic. Only runs ALTER TABLE for missing columns.
    """
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
