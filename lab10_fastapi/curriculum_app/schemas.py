"""Curriculum App HTTP request and response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class AskResponse(BaseModel):
    question: str
    sql: str
    rows: list[dict[str, Any]]
    answer: str


class CourseCreate(BaseModel):
    code: str = Field(pattern=r"^\d{8}$")
    name_th: str = Field(min_length=1, max_length=300)
    name_en: str | None = Field(default=None, max_length=300)
    credits: int = Field(ge=0, le=12)
    lecture_h: int | None = Field(default=None, ge=0, le=60)
    lab_h: int | None = Field(default=None, ge=0, le=60)
    self_h: int | None = Field(default=None, ge=0, le=60)
    description_th: str | None = None


class CourseResponse(CourseCreate):
    pass


class HealthResponse(BaseModel):
    status: str
    database: str
    database_ready: bool
    model: str
    ollama_ready: bool
    lab8b_module: str


class PlanItemResponse(BaseModel):
    program_id: str | None = None
    year: int
    semester: int
    code: str
    name_th: str | None = None
    name_en: str | None = None
    credits: int
    lecture_h: int | None = None
    lab_h: int | None = None
    self_h: int | None = None
    alt_group: str | None = None
    note: str | None = None


class PlanSummaryResponse(BaseModel):
    program_id: str | None = None
    year: int
    semester: int
    credits: int
    n_courses: int


