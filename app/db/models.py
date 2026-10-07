import datetime
import enum
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    rider_id: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reply: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )


class OpsItemStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OpsItem(Base):
    __tablename__ = "ops_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[OpsItemStatus] = mapped_column(
        String(20), nullable=False, default=OpsItemStatus.PENDING
    )
    kind: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. APPROVAL_REQUIRED, ESCALATE
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    trip_id: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
        nullable=False,
    )


class TraceRecord(Base):
    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    rider_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )


class AiHealthState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DEGRADED = "DEGRADED"


class AiHealthEvent(Base):
    __tablename__ = "ai_health_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="Gemini")
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=True)
    safe_message: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=True)
    message_id: Mapped[str] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recovered: Mapped[bool] = mapped_column(default=False, nullable=False)

    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC), nullable=False
    )
