"""
Competitor Schemas — Pydantic models for the structured competitor output.

CompetitivePayload maps 1:1 to the frontend CompetitivePayload TypeScript type
in src/types/artifacts.ts. Do not rename or add optional fields without updating
the frontend type first.

CompetitorTask is the per-competitor work unit sent via LangGraph Send API for
dynamic parallel fan-out from the planner node.
"""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class SourceItem(BaseModel):
    url: str
    title: str
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    confidence: float = Field(ge=0.0, le=1.0)


class FeatureEntry(BaseModel):
    """A single feature cell in the competitive matrix."""
    present: bool | str          # True/False or short note like "partial", "beta"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    source: SourceItem | None = None


class CompetitorRecord(BaseModel):
    name: str
    website: str
    tagline: str = ""
    features: dict[str, FeatureEntry]
    last_updated: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    recent_launches: list[str] = Field(default_factory=list)
    pricing_tier: str = ""
    sources: list[SourceItem] = Field(default_factory=list)


class CompetitivePayload(BaseModel):
    """
    The exact payload emitted as artifact_update for domain=competitive_landscape.
    Maps 1:1 to the frontend CompetitivePayload TypeScript type in src/types/artifacts.ts.
    """
    competitors: list[CompetitorRecord]
    feature_columns: list[str]
    category_summary: str
    standard_features: list[str]
    differentiator_features: list[str]
    missing_features: list[str]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceItem] = Field(default_factory=list)


class AgentEventPayload(BaseModel):
    """Wrapper matching the AgentEvent SSE contract consumed by the frontend."""
    type: Literal["artifact_update"] = "artifact_update"
    domain: Literal["competitive_landscape"] = "competitive_landscape"
    payload: CompetitivePayload


class CompetitorTask(BaseModel):
    """
    Per-competitor work unit passed via LangGraph Send for dynamic parallel fan-out.

    The planner node produces one CompetitorTask per competitor. Each task is
    dispatched to the competitor_fetch_node as a separate parallel branch.
    """
    name: str                   # Competitor display name  e.g. "Apollo.io"
    website_url: str            # Homepage URL             e.g. "https://www.apollo.io"
    changelog_url: str = ""     # Changelog/blog URL if known or guessable
    category: str = ""          # Product category passed through for context
