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
    created_at: datetime


class MarkerCreateBatch(BaseModel):
    count: int = Field(gt=0, le=500)
    person_id: Optional[int] = None


class MarkerAssign(BaseModel):
    person_id: Optional[int] = None


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
