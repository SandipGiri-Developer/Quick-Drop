import json
from pathlib import Path
from typing import Any


def load_cases(data_dir: str = "data") -> list[dict[str, Any]]:
    path = Path(data_dir) / "conversations.json"
    if not path.exists():
        raise FileNotFoundError(f"Could not find {path}")
    with open(path, "r", encoding="utf-8") as f:
        from typing import cast
        return cast(list[dict[str, Any]], json.load(f))
