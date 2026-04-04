import json
import re
from typing import Any, Dict, List, Optional

from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .models import GroupConfig


def check_wake_condition(
    event: AstrMessageEvent,
    text: str,
    wake_type: str,
    wake_value: str,
) -> bool:
    wake_type = (wake_type or "always").strip().lower()
    text = text or ""

    if wake_type == "always":
        return True

    if wake_type == "keyword":
        try:
            keywords = json.loads(wake_value or "[]")
            if not isinstance(keywords, list):
                return False
        except Exception:
            return False
        lowered = text.lower()
        return any(str(k).lower() in lowered for k in keywords if str(k).strip())

    if wake_type == "prefix":
        prefix = str(wake_value or "")
        return bool(prefix) and text.startswith(prefix)

    if wake_type == "mention":
        return is_mentioned(event)

    if wake_type == "regex":
        pattern = str(wake_value or "")
        if not pattern:
            return False
        try:
            return re.search(pattern, text) is not None
        except re.error:
            return False

    return False


def should_allow_message(
    event: AstrMessageEvent,
    cfg: Optional[GroupConfig],
    default_action: str,
) -> bool:
    if cfg is None or not cfg.enabled:
        return str(default_action).lower() != "silent"

    user_id = get_user_id(event)
    if user_id and user_id in set(cfg.blacklist):
        return False

    if not user_id or user_id not in set(cfg.whitelist):
        return False

    text = get_text(event)
    return check_multi_wake_conditions(event, text, cfg.wake_mode, cfg.wake_rules, cfg.wake_type, cfg.wake_value)


def check_multi_wake_conditions(
    event: AstrMessageEvent,
    text: str,
    wake_mode: str,
    wake_rules: List[Dict[str, Any]],
    fallback_wake_type: str,
    fallback_wake_value: str,
) -> bool:
    rules = wake_rules if isinstance(wake_rules, list) else []
    if not rules:
        return check_wake_condition(event, text, fallback_wake_type, fallback_wake_value)

    results: List[bool] = []
    for item in rules:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type", "")).strip().lower()
        if not t:
            continue

        v = item.get("value", "")
        wake_value_str = ""
        if t == "keyword":
            if isinstance(v, list):
                wake_value_str = json.dumps([str(x).strip() for x in v if str(x).strip()], ensure_ascii=False)
            else:
                wake_value_str = str(v or "")
        elif t in {"prefix", "regex"}:
            wake_value_str = str(v or "")
        else:
            wake_value_str = ""

        results.append(check_wake_condition(event, text, t, wake_value_str))

    if not results:
        return check_wake_condition(event, text, fallback_wake_type, fallback_wake_value)

    mode = str(wake_mode or "any").strip().lower()
    if mode == "all":
        return all(results)
    return any(results)


def is_group_message(event: AstrMessageEvent) -> bool:
    if hasattr(event, "is_group") and callable(getattr(event, "is_group")):
        try:
            return bool(event.is_group())
        except Exception:
            pass

    if hasattr(event, "message_type"):
        try:
            return str(getattr(event, "message_type")).lower() == "group"
        except Exception:
            pass

    if hasattr(event, "get_message_type") and callable(getattr(event, "get_message_type")):
        try:
            return str(event.get_message_type()).lower() == "group"
        except Exception:
            pass

    return bool(get_group_id(event))


def is_self_message(event: AstrMessageEvent) -> bool:
    bool_keys = ["is_self", "from_self", "self_message"]
    for key in bool_keys:
        if hasattr(event, key):
            val = getattr(event, key)
            try:
                if callable(val):
                    val = val()
                if bool(val):
                    return True
            except Exception:
                pass

    user_id = get_user_id(event)
    self_id = get_self_id(event)
    return bool(user_id and self_id and user_id == self_id)


def get_group_id(event: AstrMessageEvent) -> str:
    return get_string_from_event(event, ["group_id"], ["get_group_id"]) or ""


def get_user_id(event: AstrMessageEvent) -> str:
    return get_string_from_event(
        event,
        ["sender_id", "user_id", "qq"],
        ["get_sender_id", "get_user_id"],
    ) or ""


def get_self_id(event: AstrMessageEvent) -> str:
    return get_string_from_event(
        event,
        ["self_id", "bot_id"],
        ["get_self_id", "get_bot_id"],
    ) or ""


def get_text(event: AstrMessageEvent) -> str:
    for getter in ["get_message_str", "get_plain_text"]:
        if hasattr(event, getter):
            fn = getattr(event, getter)
            if callable(fn):
                try:
                    val = fn()
                    if val is not None:
                        return str(val)
                except Exception:
                    pass

    if hasattr(event, "message_str"):
        try:
            return str(getattr(event, "message_str") or "")
        except Exception:
            pass

    return ""


def get_string_from_event(
    event: AstrMessageEvent,
    attr_candidates: List[str],
    method_candidates: List[str],
) -> Optional[str]:
    for attr in attr_candidates:
        if hasattr(event, attr):
            try:
                val = getattr(event, attr)
                if callable(val):
                    val = val()
                if val is not None and str(val).strip():
                    return str(val).strip()
            except Exception:
                pass

    for method in method_candidates:
        if hasattr(event, method):
            fn = getattr(event, method)
            if callable(fn):
                try:
                    val = fn()
                    if val is not None and str(val).strip():
                        return str(val).strip()
                except Exception:
                    pass

    return None


def is_mentioned(event: AstrMessageEvent) -> bool:
    for key in ["is_at_me", "is_mentioned"]:
        if hasattr(event, key):
            val = getattr(event, key)
            try:
                if callable(val):
                    val = val()
                if bool(val):
                    return True
            except Exception:
                pass

    bot_id = get_self_id(event)
    if hasattr(event, "get_messages") and callable(getattr(event, "get_messages")):
        try:
            chain = event.get_messages() or []
            for seg in chain:
                if seg is None:
                    continue
                seg_type = type(seg).__name__.lower()
                if "at" not in seg_type:
                    continue

                seg_target = ""
                for key in ["qq", "user_id", "target", "uid"]:
                    if hasattr(seg, key):
                        v = getattr(seg, key)
                        if callable(v):
                            v = v()
                        if v is not None:
                            seg_target = str(v)
                            break

                if not bot_id:
                    return True
                if seg_target and seg_target == bot_id:
                    return True
        except Exception:
            pass

    text = get_text(event)
    if bot_id and f"@{bot_id}" in text:
        return True

    return False


def interrupt_result():
    for method_name in ["interrupt", "stop", "block"]:
        fn = getattr(MessageEventResult, method_name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return False


def is_management_command(text: str) -> bool:
    t = (text or "").strip().lower().lstrip("/")
    return (
        t.startswith("开启过滤器管理")
        or t.startswith("关闭过滤器管理")
        or t.startswith("过滤器管理状态")
        or t.startswith("设置过滤器管理端口")
    )


def extract_port_from_text(text: str) -> Optional[int]:
    m = re.search(r"(\d{2,5})", text or "")
    if not m:
        return None
    port = int(m.group(1))
    if 1 <= port <= 65535:
        return port
    return None
