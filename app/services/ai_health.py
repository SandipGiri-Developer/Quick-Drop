import threading
import time
import datetime
from sqlalchemy.orm import Session
from app.db.models import AiHealthEvent, AiHealthState
from typing import Any
import os

class AiHealthTracker:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.state = AiHealthState.HEALTHY
        self.last_error = None
        self.last_error_time = None
        self.last_request_time = 0.0

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _wait_for_rate_limit(self):
        """Ensure 3-4 seconds between requests."""
        if os.getenv("TESTING") == "1":
            return # Don't delay in fast tests
            
        MIN_INTERVAL = 3.5  
        with self._lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - elapsed)
            self.last_request_time = time.time()

    def record_event(self, db: Session, provider: str, error_type: str, safe_message: str, status_code: int = None, is_success: bool = False):
        with self._lock:
            if is_success:
                if self.state != AiHealthState.HEALTHY:
                    self.state = AiHealthState.HEALTHY
                event = AiHealthEvent(
                    provider=provider,
                    error_type="SUCCESS",
                    status_code=200,
                    safe_message="Recovered to HEALTHY",
                    recovered=True
                )
                db.add(event)
                try:
                    db.commit()
                except:
                    db.rollback()
                return

            if status_code == 429:
                self.state = AiHealthState.RATE_LIMITED
            elif status_code in (401, 403) or "auth" in safe_message.lower() or "key" in safe_message.lower():
                self.state = AiHealthState.AUTHENTICATION_ERROR
            elif status_code == 402 or "quota" in safe_message.lower() or "exhausted" in safe_message.lower():
                self.state = AiHealthState.QUOTA_EXHAUSTED
            elif error_type == "TIMEOUT":
                self.state = AiHealthState.TIMEOUT
            else:
                self.state = AiHealthState.PROVIDER_ERROR

            self.last_error = safe_message
            self.last_error_time = datetime.datetime.now(datetime.UTC)

            # Mask potential keys
            safe_msg = safe_message.replace("API_KEY", "***")
            for token in safe_msg.split():
                if len(token) > 20 and ("Aiz" in token or "gsk_" in token):
                    safe_msg = safe_msg.replace(token, "***")

            event = AiHealthEvent(
                provider=provider,
                error_type=error_type,
                status_code=status_code,
                safe_message=safe_msg[:1000],
                recovered=False
            )
            db.add(event)
            try:
                db.commit()
            except:
                db.rollback()

    def get_health_status(self, db: Session) -> dict[str, Any]:
        with self._lock:
            events = db.query(AiHealthEvent).order_by(AiHealthEvent.occurred_at.desc()).limit(15).all()
            recent_events = [
                {
                    "time": e.occurred_at.strftime("%H:%M:%S"),
                    "type": e.error_type,
                    "status": e.status_code,
                    "message": e.safe_message
                }
                for e in events
            ]
            return {
                "provider": os.getenv("LLM_PROVIDER", "google"),
                "status": self.state.value,
                "last_error": self.last_error,
                "last_error_time": self.last_error_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_error_time else None,
                "recent_events": recent_events
            }
