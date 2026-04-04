from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import json
import sqlite3


@dataclass
class GroupConfig:
    group_id: str
    enabled: bool
    whitelist: List[str]
    blacklist: List[str]
    wake_type: str
    wake_value: str
    wake_mode: str
    wake_rules: List[Dict[str, Any]]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "GroupConfig":
        whitelist_raw = row["whitelist"] or "[]"
        blacklist_raw = row["blacklist"] if "blacklist" in row.keys() else "[]"
        wake_value_raw = row["wake_value"] or ""
        wake_mode_raw = row["wake_mode"] if "wake_mode" in row.keys() else "any"
        wake_rules_raw = row["wake_rules"] if "wake_rules" in row.keys() else "[]"

        try:
            whitelist = json.loads(whitelist_raw)
            if not isinstance(whitelist, list):
                whitelist = []
        except Exception:
            whitelist = []

        whitelist = [str(x).strip() for x in whitelist if str(x).strip()]

        try:
            blacklist = json.loads(blacklist_raw or "[]")
            if not isinstance(blacklist, list):
                blacklist = []
        except Exception:
            blacklist = []
        blacklist = [str(x).strip() for x in blacklist if str(x).strip()]

        wake_mode = str(wake_mode_raw or "any").strip().lower()
        if wake_mode not in {"any", "all"}:
            wake_mode = "any"

        try:
            wake_rules = json.loads(wake_rules_raw or "[]")
            if not isinstance(wake_rules, list):
                wake_rules = []
        except Exception:
            wake_rules = []

        normalized_rules: List[Dict[str, Any]] = []
        for item in wake_rules:
            if not isinstance(item, dict):
                continue
            t = str(item.get("type", "")).strip().lower()
            v = item.get("value", "")
            if not t:
                continue
            normalized_rules.append({"type": t, "value": v})

        # 兼容旧数据：没有多规则时，自动降级为单规则。
        if not normalized_rules:
            legacy_type = str(row["wake_type"] or "always").strip().lower()
            legacy_value: Any = wake_value_raw
            if legacy_type == "keyword":
                try:
                    parsed = json.loads(wake_value_raw or "[]")
                    legacy_value = parsed if isinstance(parsed, list) else []
                except Exception:
                    legacy_value = []
            normalized_rules = [{"type": legacy_type, "value": legacy_value}]

        return cls(
            group_id=str(row["group_id"]),
            enabled=bool(row["enabled"]),
            whitelist=whitelist,
            blacklist=blacklist,
            wake_type=str(row["wake_type"] or "always"),
            wake_value=str(wake_value_raw),
            wake_mode=wake_mode,
            wake_rules=normalized_rules,
        )

    def to_db_tuple(self) -> Tuple[str, int, str, str, str, str, str, str]:
        return (
            self.group_id,
            1 if self.enabled else 0,
            json.dumps(self.whitelist, ensure_ascii=False),
            json.dumps(self.blacklist, ensure_ascii=False),
            self.wake_type,
            self.wake_value,
            self.wake_mode,
            json.dumps(self.wake_rules, ensure_ascii=False),
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
            "blacklist": self.blacklist,
            "wake_type": self.wake_type,
            "wake_value": wake_value,
            "wake_mode": self.wake_mode,
            "wake_rules": self.wake_rules,
        }
