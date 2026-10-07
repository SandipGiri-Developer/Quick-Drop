from typing import Any

from sqlalchemy.orm import Session

from app.db.models import TraceRecord


class TraceService:
    @staticmethod
    def add_trace(
        db: Session,
        rider_id: str,
        action_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceRecord:
        record = TraceRecord(
            rider_id=rider_id,
            action_type=action_type,
            content=content,
            metadata_json=metadata or {},
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
