"""Data contracts shared by every stage of the pipeline."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Label(str, Enum):
    VERIFIED = "VERIFIED"
    FALSE = "FALSE"
    OUTDATED = "OUTDATED"
    PARTLY_SUPPORTED = "PARTLY_SUPPORTED"
    CANNOT_BE_CONFIRMED = "CANNOT_BE_CONFIRMED"


class Claim(BaseModel):
    id: str = ""
    text: str
    text_en: str
    category: str = "other"
    time_sensitive: bool = False
    check_worthiness: int = 5
    search_queries: list[str] = Field(default_factory=list)


class ClaimList(BaseModel):
    """LLM output of the extraction stage."""
    language: str = "en"
    claims: list[Claim] = Field(default_factory=list)
    no_claims_reason: str = ""


class Evidence(BaseModel):
    id: str
    source_name: str
    domain: str
    url: str
    published_at: str | None = None
    snippet: str
    kind: str = "web"  # "fact_check_db" | "web"
    rating: str | None = None
    relevance: float = 0.0


class Verdict(BaseModel):
    label: Label
    what_is_wrong: str = ""
    summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_stances: dict[str, str] = Field(default_factory=dict)  # id -> supports|contradicts|related
    confidence: str = "low"  # high | medium | low
    reasoning_en: str = ""


class ClaimResult(BaseModel):
    claim: Claim
    verdict: Verdict
    evidence: list[Evidence] = Field(default_factory=list)
    cached: bool = False
    guardrail_note: str | None = None


class Ingested(BaseModel):
    text: str
    input_type: str  # text | image | audio | pdf | url
    source_url: str | None = None
    source_date: str | None = None
    note: str | None = None


class CheckResult(BaseModel):
    input_type: str
    language: str
    source_url: str | None = None
    source_date: str | None = None
    extracted_text_preview: str = ""
    results: list[ClaimResult] = Field(default_factory=list)
    note: str | None = None
    elapsed_ms: int = 0
    providers_used: list[str] = Field(default_factory=list)
