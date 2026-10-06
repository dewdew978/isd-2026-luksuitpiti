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
    sources: list[dict[str, Any]] = Field(default_factory=list)


class CourseCreate(BaseModel):
    code: str = Field(pattern=r"^\d{8}$")
    name_th: str = Field(min_length=1, max_length=300)
    name_en: str | None = Field(default=None, max_length=300)
    credits: int = Field(ge=0, le=12)
    lecture_h: int | None = Field(default=None, ge=0, le=60)
    lab_h: int | None = Field(default=None, ge=0, le=60)
    self_h: int | None = Field(default=None, ge=0, le=60)
    description_th: str | None = None
    pdf_pages: str | None = None
    printed_pages: str | None = None


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


class StatsResponse(BaseModel):
    program_id: str | None = None
    total_courses: int
    total_credits: int
    total_lecture_hours: int
    total_lab_hours: int
    total_self_hours: int = 0


class PrerequisiteItem(BaseModel):
    code: str = Field(description="รหัสวิชา")
    name_th: str | None = Field(default=None, description="ชื่อวิชา (ภาษาไทย)")
    name_en: str | None = Field(default=None, description="ชื่อวิชา (ภาษาอังกฤษ)")
    kind: str = Field(default="pre", description="ประเภทเงื่อนไข (pre หรือ co)")
    credits: int | None = Field(default=None, description="หน่วยกิต")


class CoursePrerequisitesResponse(BaseModel):
    code: str = Field(description="รหัสวิชา")
    name_th: str | None = Field(default=None, description="ชื่อวิชา (ภาษาไทย)")
    name_en: str | None = Field(default=None, description="ชื่อวิชา (ภาษาอังกฤษ)")
    credits: int | None = Field(default=None, description="หน่วยกิตของวิชานี้")
    requires: list[PrerequisiteItem] = Field(
        default_factory=list,
        description="วิชาที่ต้องเรียนมาก่อนวิชานี้ (prerequisites)",
    )
    prerequisites: list[PrerequisiteItem] = Field(
        default_factory=list,
        description="วิชาที่ต้องเรียนมาก่อนวิชานี้ (alias for requires)",
    )
    required_by: list[PrerequisiteItem] = Field(
        default_factory=list,
        description="วิชาที่วิชานี้เป็นวิชาบังคับก่อนให้ (courses that require this course)",
    )


class RegulationResponse(BaseModel):
    id: int
    program_id: str | None = None
    category: str
    topic: str
    condition_desc: str | None = None
    min_gpa: float | None = None
    max_gpa: float | None = None
    min_credits: int | None = None
    max_credits: int | None = None
    penalty_action: str | None = None
    article_no: str | None = None
    source_page: int | None = None
