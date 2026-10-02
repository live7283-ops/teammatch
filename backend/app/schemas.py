"""Pydantic request/response models."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---- Auth ------------------------------------------------------
class SignupRequest(BaseModel):
    role: Literal["student", "professor"]
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    # student
    major: str | None = None
    year: int | None = Field(default=None, ge=1, le=6)
    student_id: str | None = None
    # professor
    dept: str | None = None
    school: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


class UserOut(BaseModel):
    id: uuid.UUID
    role: str
    name: str
    email: EmailStr
    major: str | None = None
    year: int | None = None
    student_id: str | None = None
    bio: str | None = None
    dept: str | None = None
    school: str | None = None

    model_config = {"from_attributes": True}


# ---- Classes ---------------------------------------------------
class ClassCreate(BaseModel):
    name: str
    code: str
    term: str
    capacity: int = 40
    kind: str | None = None
    survey_deadline: dt.datetime | None = None


class ClassOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    term: str
    capacity: int
    join_code: str
    kind: str | None
    status: str
    survey_deadline: dt.datetime | None
    submitted: int = 0
    enrolled: int = 0

    model_config = {"from_attributes": True}


class JoinRequest(BaseModel):
    join_code: str


# ---- Survey / profile ------------------------------------------
class SkillIn(BaseModel):
    name: str
    level: int = Field(ge=1, le=5)


class AvailabilitySlot(BaseModel):
    day: int = Field(ge=0, le=6)
    block: int = Field(ge=0)
    state: Literal["y", "n"]


class Traits(BaseModel):
    pace: int | None = Field(default=None, ge=1, le=5)
    prep: int | None = Field(default=None, ge=1, le=5)
    lead: int | None = Field(default=None, ge=1, le=5)
    comm: int | None = Field(default=None, ge=1, le=5)


class SurveySubmit(BaseModel):
    roles: list[str] = []
    skills: list[SkillIn] = []
    traits: Traits = Traits()
    availability: list[AvailabilitySlot] = []
    match_ready: bool = False


class SurveyOut(SurveySubmit):
    enrollment_id: uuid.UUID
    updated_at: dt.datetime | None = None


# ---- Matching --------------------------------------------------
class Weights(BaseModel):
    major: int = Field(ge=1, le=5)
    role: int = Field(ge=1, le=5)
    time: int = Field(ge=1, le=5)
    trait: int = Field(ge=1, le=5)


class HardConstraints(BaseModel):
    same_major: bool = False
    fix_pair: bool = False
    split_pair: bool = False
    even_transfer: bool = False


class MatchRequest(BaseModel):
    team_size: int = Field(ge=2, le=8)
    weights: Weights
    hard: HardConstraints = HardConstraints()
    note: str | None = None


class MemberOut(BaseModel):
    student_id: uuid.UUID
    name: str
    major: str | None
    year: int | None
    assigned_role: str | None


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    fit_score: float
    members: list[MemberOut]


class MatchResultOut(BaseModel):
    run_id: uuid.UUID
    class_id: uuid.UUID
    team_size: int
    avg_score: float
    teams: list[TeamOut]


class PresetOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    team_size: int
    weights: Weights
    hard: HardConstraints
    is_builtin: bool

    model_config = {"from_attributes": True}
