import logging

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.message import MessageRequest, MessageResponse
from app.services.message_service import process_message

logger = logging.getLogger(__name__)

from app.api import ops

app = FastAPI(title="QuickDrop Rider Payout Dispute Desk")
app.include_router(ops.router)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:  # noqa: B008
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Healthcheck failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.post("/messages", response_model=MessageResponse)
def handle_message(request: MessageRequest, db: Session = Depends(get_db)) -> MessageResponse:  # noqa: B008
    try:
        reply = process_message(db, request)
        return MessageResponse(reply=reply)
    except Exception:
        logger.exception("Failed to process message")
        raise HTTPException(status_code=500, detail="Internal server error")
