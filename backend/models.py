"""Pydantic contracts shared by the API, event engine, and dashboard."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TrainStatus(StrEnum):
    ON_TIME = "On Time"
    DELAYED = "Delayed"
    APPROACHING = "Approaching"
    PLATFORM_CHANGED = "Platform Changed"


class TrainRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    train_no: str
    train_name: str
    origin: str
    destination: str
    scheduled_arrival: str = Field(description="Station-local time in HH:MM format")
    estimated_arrival: str = Field(description="Station-local time in HH:MM format")
    delay_minutes: int = Field(ge=0)
    platform: str
    status: TrainStatus
    updated_at: datetime


class TrainUpdate(BaseModel):
    train_name: str | None = None
    estimated_arrival: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    delay_minutes: int | None = Field(default=None, ge=0)
    platform: str | None = None
    status: TrainStatus | None = None


class ManualAnnouncementRequest(BaseModel):
    train_no: str
    reason: str = Field(default="Operator requested announcement", max_length=240)


class HoldRequest(BaseModel):
    reason: str = Field(default="Held by operator", max_length=240)


class Announcement(BaseModel):
    id: str
    train_no: str
    train_name: str
    trigger: str
    status: str = "pending"
    scripts: dict[str, str]
    created_at: datetime
    updated_at: datetime


class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    action: str
    message: str
    train_no: str | None = None
    announcement_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
