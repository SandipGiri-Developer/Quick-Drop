from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from app.db.models import MessageRecord
from app.schemas.message import MessageRequest
from app.services.agent import run_agent


def process_message(db: Session, request: MessageRequest) -> str:
    """
    Processes a message idempotently using the database.
    """
    # 1. Check if already processed (fast path)
    existing = (
        db.query(MessageRecord).filter(MessageRecord.message_id == request.message_id).first()
    )
    if existing:
        return existing.reply

    # 2. Load conversation history
    previous_records = (
        db.query(MessageRecord)
        .filter(MessageRecord.rider_id == request.rider_id)
        .order_by(MessageRecord.received_at.asc())
        .all()
    )

    from langchain_core.messages import BaseMessage

    history: list[BaseMessage] = []
    for record in previous_records:
        history.append(HumanMessage(content=record.text))
        history.append(AIMessage(content=record.reply))

    # 3. Process new message via LangGraph Agent
    try:
        reply = run_agent(
            rider_id=request.rider_id,
            db=db,
            history=history,
            current_text=request.text,
        )
    except Exception as e:  # noqa: BLE001
        reply = f"I'm sorry, our system is currently experiencing issues. Please try again later. (Error: {e})"

    # 4. Persist and handle concurrent races safely
    record = MessageRecord(
        message_id=request.message_id,
        rider_id=request.rider_id,
        text=request.text,
        received_at=request.received_at,
        reply=reply,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        # A concurrent request inserted the same message_id, or DB driver locked
        db.rollback()
        existing_concurrent = (
            db.query(MessageRecord).filter(MessageRecord.message_id == request.message_id).first()
        )
        if existing_concurrent:
            return existing_concurrent.reply
        raise  # Reraise if it's some other error

    return reply
