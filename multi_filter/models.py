from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import json
import sqlite3


VALID_RULE_TYPES = {"keyword", "prefix", "regex", "mention", "always"}


def _normalize_rule_item(item: Any) -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    t = str(item.get("type", "") or "").strip().lower()
    if t not in VALID_RULE_TYPES:
        return None
    invert = bool(item.get("invert", False))
    value = item.get("value", "")
    if t in {"mention", "always"}:
        value = ""
    return {"type": t, "value": value, "invert": invert}


def _normalize_rule_group(item: Any, default_mode: str = "any") -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    group_mode = str(item.get("group_mode", item.get("mode", default_mode)) or default_mode).strip().lower()
    if group_mode not in {"any", "all"}:
        group_mode = default_mode if default_mode in {"any", "all"} else "any"
    raw_rules = item.get("rules", [])
    if not isinstance(raw_rules, list):
        return None

    rules: List[Dict[str, Any]] = []
    for raw_rule in raw_rules:
        rule = _normalize_rule_item(raw_rule)
        if rule is not None:
            rules.append(rule)

    if not rules:
        return None

    return {"group_mode": group_mode, "rules": rules}


def _normalize_rule_groups(raw_rules: Any, default_mode: str = "any") -> List[Dict[str, Any]]:
    if not isinstance(raw_rules, list):
        return []

    has_group_structure = any(isinstance(item, dict) and ("rules" in item or "group_mode" in item or "mode" in item) for item in raw_rules)
    if has_group_structure:
        groups: List[Dict[str, Any]] = []
        for item in raw_rules:
            group = _normalize_rule_group(item, default_mode=default_mode)
            if group is not None:
                groups.append(group)
        return groups

    flat_rules: List[Dict[str, Any]] = []
    for item in raw_rules:
        rule = _normalize_rule_item(item)
        if rule is not None:
            flat_rules.append(rule)

    if not flat_rules:
        return []

    return [{"group_mode": default_mode if default_mode in {"any", "all"} else "any", "rules": flat_rules}]


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

        normalized_groups: List[Dict[str, Any]] = []
        has_group_structure = any(isinstance(item, dict) and ("rules" in item or "group_mode" in item or "mode" in item) for item in wake_rules)
        if has_group_structure:
            for item in wake_rules:
                group = _normalize_rule_group(item, default_mode=wake_mode)
                if group is not None:
                    normalized_groups.append(group)
        else:
            flat_rules: List[Dict[str, Any]] = []
            for item in wake_rules:
                rule = _normalize_rule_item(item)
                if rule is not None:
                    flat_rules.append(rule)
            if flat_rules:
                normalized_groups = [{"group_mode": wake_mode, "rules": flat_rules}]

        return cls(
            group_id=str(row["group_id"]),
            enabled=bool(row["enabled"]),
            whitelist=whitelist,
            blacklist=blacklist,
            wake_type=str(row["wake_type"] or "always"),
            wake_value=str(wake_value_raw),
            wake_mode=wake_mode,
            wake_rules=normalized_groups,
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
