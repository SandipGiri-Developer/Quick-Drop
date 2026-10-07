from typing import Any

import httpx


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0)

    def send_message(self, rider_id: str, message_id: str, text: str, received_at: str) -> dict[str, Any]:
        resp = self.client.post(f"{self.base_url}/messages", json={
            "message_id": message_id,
            "rider_id": rider_id,
            "text": text,
            "received_at": received_at
        })
        resp.raise_for_status()
        from typing import cast
        return cast(dict[str, Any], resp.json())

    def get_trace(self, rider_id: str) -> list[dict[str, Any]]:
        resp = self.client.get(f"{self.base_url}/trace/{rider_id}")
        resp.raise_for_status()
        from typing import cast
        return cast(list[dict[str, Any]], resp.json())

    def get_pending_ops(self) -> list[dict[str, Any]]:
        resp = self.client.get(f"{self.base_url}/ops/pending")
        resp.raise_for_status()
        from typing import cast
        return cast(list[dict[str, Any]], resp.json())

    def get_health(self) -> dict[str, Any]:
        resp = self.client.get(f"{self.base_url}/health")
        resp.raise_for_status()
        from typing import cast
        return cast(dict[str, Any], resp.json())

class PaySwiftClientAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    def get_payouts(self, rider_id: str) -> list[dict[str, Any]]:
        import time
        for _ in range(5):
            try:
                resp = self.client.get(f"{self.base_url}/v1/payouts?rider_id={rider_id}")
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                from typing import cast
                return cast(list[dict[str, Any]], resp.json().get("data", []))
            except Exception as e:
                time.sleep(1.0)
        return []

    def trigger_chaos(self, enabled: bool) -> None:
        import time
        for _ in range(5):
            try:
                if enabled:
                    resp = self.client.post(f"{self.base_url}/admin/outage", json={"seconds": 10})
                else:
                    resp = self.client.post(f"{self.base_url}/admin/outage", json={"seconds": 0})
                resp.raise_for_status()
                return
            except Exception as e:
                time.sleep(1.0)
