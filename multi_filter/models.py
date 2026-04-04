from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import json
import sqlite3


@dataclass
class GroupConfig:
    group_id: str
    enabled: bool
    whitelist: List[str]
    wake_type: str
    wake_value: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GroupConfig":
        whitelist_raw = row["whitelist"] or "[]"
        wake_value_raw = row["wake_value"] or ""

        try:
            whitelist = json.loads(whitelist_raw)
            if not isinstance(whitelist, list):
                whitelist = []
        except Exception:
            whitelist = []

        whitelist = [str(x).strip() for x in whitelist if str(x).strip()]

        return cls(
            group_id=str(row["group_id"]),
            enabled=bool(row["enabled"]),
            whitelist=whitelist,
            wake_type=str(row["wake_type"] or "always"),
            wake_value=str(wake_value_raw),
        )

    def to_db_tuple(self) -> Tuple[str, int, str, str, str]:
        return (
            self.group_id,
            1 if self.enabled else 0,
            json.dumps(self.whitelist, ensure_ascii=False),
            self.wake_type,
            self.wake_value,
        )

    def to_api_dict(self) -> Dict[str, Any]:
        wake_value: Any = self.wake_value
        if self.wake_type == "keyword":
            try:
                parsed = json.loads(self.wake_value or "[]")
                wake_value = parsed if isinstance(parsed, list) else []
            except Exception:
                wake_value = []
        return {
            "group_id": self.group_id,
            "enabled": self.enabled,
            "whitelist": self.whitelist,
            "wake_type": self.wake_type,
            "wake_value": wake_value,
        }
