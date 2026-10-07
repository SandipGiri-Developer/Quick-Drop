import datetime
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import OpsItem, OpsItemStatus, TraceRecord
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# Schema models
class TraceResponse(BaseModel):
    id: int
    rider_id: str
    action_type: str
    content: str
    metadata_json: dict[str, Any] | None
    created_at: datetime.datetime


class OpsItemResponse(BaseModel):
    id: int
    rider_id: str
    status: OpsItemStatus
    kind: str
    amount: int
    reason: str
    trip_id: str | None
    created_at: datetime.datetime


@router.get("/ops", response_class=HTMLResponse)
def get_ops_page() -> HTMLResponse:
    import os

    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "templates", "ops.html"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@router.get("/trace/{rider_id}", response_model=list[TraceResponse])
def get_trace(rider_id: str, db: Session = Depends(get_db)) -> list[TraceResponse]:  # noqa: B008
    traces = (
        db.query(TraceRecord)
        .filter(TraceRecord.rider_id == rider_id)
        .order_by(TraceRecord.created_at.asc())
        .all()
    )
    if not traces:
        # According to standard APIs, return empty list or 404, let's return empty list for clarity
        return []
    return [
        TraceResponse(
            id=t.id,
            rider_id=t.rider_id,
            action_type=t.action_type,
            content=t.content,
            metadata_json=t.metadata_json,
            created_at=t.created_at,
        )
        for t in traces
    ]


@router.get("/ops/pending", response_model=list[OpsItemResponse])
def get_pending_ops(db: Session = Depends(get_db)) -> list[OpsItemResponse]:  # noqa: B008
    items = (
        db.query(OpsItem)
        .filter(OpsItem.status == OpsItemStatus.PENDING)
        .order_by(OpsItem.created_at.desc())
        .all()
    )
    return [
        OpsItemResponse(
            id=i.id,
            rider_id=i.rider_id,
            status=i.status,
            kind=i.kind,
            amount=i.amount,
            reason=i.reason,
            trip_id=i.trip_id,
            created_at=i.created_at,
        )
        for i in items
    ]


@router.post("/ops/pending/{item_id}/approve")
def approve_ops_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
    # 1. Lock the row to prevent concurrent approval (select for update)
    item = db.query(OpsItem).filter(OpsItem.id == item_id).with_for_update().first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 2. Check actionable status
    if item.status != OpsItemStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Item is no longer actionable (Status: {item.status})"
        )

    try:
        from app.core.config import settings
        from app.infrastructure.payswift.client import PaySwiftClient
        from app.infrastructure.payswift.models import PaySwiftRequest
        from app.services.trace_service import TraceService

        payswift = PaySwiftClient(str(settings.payswift_base_url))
        payment_ref = f"ops_approval_{item.rider_id}_{item.id}"

        # 3. Pay via PaySwift using safe idempotency key
        req = PaySwiftRequest(rider_id=item.rider_id, amount=item.amount, reference=payment_ref)
        resp = payswift.pay_safely(request=req, idempotency_key=payment_ref)

        # 4. Mark as APPROVED
        item.status = OpsItemStatus.APPROVED

        # 5. Add trace
        TraceService.add_trace(
            db,
            item.rider_id,
            "OPS_APPROVED",
            f"Ops approved payment of ₹{item.amount}. PaySwift Ref: {resp.reference}",
        )

        db.commit()
        return {"status": "success", "message": "Approved and paid", "reference": resp.reference}

    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error(f"Approval failed for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute payment: {e!s}")


@router.post("/ops/pending/{item_id}/reject")
def reject_ops_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
    item = db.query(OpsItem).filter(OpsItem.id == item_id).with_for_update().first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.status != OpsItemStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Item is no longer actionable (Status: {item.status})"
        )

    try:
        from app.services.trace_service import TraceService

        item.status = OpsItemStatus.REJECTED
        TraceService.add_trace(db, item.rider_id, "OPS_REJECTED", f"Ops rejected item {item_id}.")

        db.commit()
        return {"status": "success", "message": "Rejected"}

    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error(f"Rejection failed for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject item")


@router.get("/ops/ai-health")
def get_ai_health(db: Session = Depends(get_db)) -> dict[str, Any]:  # noqa: B008
    from app.services.ai_health import AiHealthTracker

    tracker = AiHealthTracker.get_instance()
    return tracker.get_health_status(db)
