"""Wire contracts for the Assistant module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LlmModelOut(BaseModel):
    name: str
    size_gb: float
    parameter_size: str | None
    default: bool


class LlmModels(BaseModel):
    models: list[LlmModelOut]
    reachable: bool
    default: str


class EnhanceRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=2000)
    model: str | None = Field(default=None, max_length=200)
    adult: bool = False


class EnhanceResponse(BaseModel):
    prompt: str
    negative: str
    model: str
    seconds: float
