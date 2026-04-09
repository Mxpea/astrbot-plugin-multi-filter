import json
import re
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from .models import GroupConfig


def _split_tokens(raw: str) -> List[str]:
    s = str(raw or "").replace("，", ",").replace("；", ";")
    # 通用分隔符: 逗号/分号/竖线/换行（仅用于 keyword/prefix）
    parts = re.split(r"[,;|\n\r]+", s)
    return [p.strip() for p in parts if p and p.strip()]


def _split_types(raw: str) -> List[str]:
    # 唤醒类型允许 | 连接多个类型。
    parts = re.split(r"[|,;/\n\r]+", str(raw or ""))
    return [p.strip().lower() for p in parts if p and p.strip()]


def _parse_keyword_values(wake_value: str) -> List[str]:
    raw = wake_value or ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        if isinstance(parsed, str):
            return _split_tokens(parsed)
    except Exception:
        pass
    return _split_tokens(raw)


def _parse_regex_values(wake_value: Any) -> List[str]:
    if isinstance(wake_value, list):
        return [str(x).strip() for x in wake_value if str(x).strip()]
    raw = str(wake_value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in re.split(r"[\n\r]+", raw) if x and x.strip()]


def _candidate_values_for_type(rule_type: str, wake_value: Any) -> List[str]:
    if rule_type == "keyword":
        return _parse_keyword_values(str(wake_value or ""))
    if rule_type == "prefix":
        return _split_tokens(str(wake_value or ""))
    if rule_type == "regex":
        return _parse_regex_values(wake_value)
    return [""]


def _evaluate_rule_entry(event: AstrMessageEvent, text: str, rule: Dict[str, Any]) -> bool:
    if not isinstance(rule, dict):
        return False

    rule_type = str(rule.get("type", "") or "").strip().lower()
    if not rule_type:
        return False

    raw_types = _split_types(rule_type)
    if not raw_types:
        return False

    invert = bool(rule.get("invert", False))
    value = rule.get("value", "")

    hit = False
    for single_type in raw_types:
        candidates = _candidate_values_for_type(single_type, value)
        if not candidates:
            candidates = [""]

        for single_value in candidates:
            if single_type == "keyword":
                wake_value_str = json.dumps([single_value], ensure_ascii=False)
            elif single_type in {"prefix", "regex"}:
                wake_value_str = str(single_value or "")
            else:
                wake_value_str = ""

            if check_wake_condition(event, text, single_type, wake_value_str):
                hit = True
                break
        if hit:
            break

    return (not hit) if invert else hit


def _evaluate_rule_group(event: AstrMessageEvent, text: str, group: Dict[str, Any]) -> bool:
    if not isinstance(group, dict):
        return False

    raw_rules = group.get("rules", [])
    if not isinstance(raw_rules, list):
        raw_rules = []

    rules = [item for item in raw_rules if isinstance(item, dict)]
    if not rules and "type" in group:
        rules = [group]

    if not rules:
        return False

    group_mode = str(group.get("group_mode", group.get("mode", "any")) or "any").strip().lower()
    if group_mode not in {"any", "all"}:
        group_mode = "any"

    results = [_evaluate_rule_entry(event, text, rule) for rule in rules]
    if group_mode == "all":
        return all(results)
    return any(results)


def _is_safe_regex(pattern: str) -> bool:
    # 轻量防护：拒绝过长规则和常见灾难回溯写法，降低 ReDoS 风险。
    p = str(pattern or "")
    if not p or len(p) > 256:
        return False
    suspicious = [
        r"(a+)+",
        r"(.*)+",
        r"(.+)+",
        r"(\\w+)+",
        r"(\\d+)+",
        r"(\\s+)+",
        r"(a*)+",
        r"(.*)*",
    ]
    low = p.lower()
    return not any(s in low for s in suspicious)


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
        keywords = _parse_keyword_values(wake_value)
        if not keywords:
            return False
        lowered = text.lower()
        return any(str(k).lower() in lowered for k in keywords if str(k).strip())

    if wake_type == "prefix":
        prefixes = _split_tokens(str(wake_value or ""))
        if not prefixes:
            return False
        return any(text.startswith(p) for p in prefixes if p)

    if wake_type == "mention":
        return is_mentioned(event)

    if wake_type == "regex":
        patterns = [x.strip() for x in re.split(r"[\n\r]+", str(wake_value or "")) if x and x.strip()]
        if not patterns:
            return False
        for pattern in patterns:
            if not _is_safe_regex(pattern):
                continue
            try:
                compiled = re.compile(pattern)
                if compiled.search(text) is not None:
                    return True
            except re.error:
                continue
        return False

    return False


def should_allow_message(
    event: AstrMessageEvent,
    cfg: Optional[GroupConfig],
    default_action: str,
) -> bool:
    allowed, _ = should_allow_message_with_reason(event, cfg, default_action)
    return allowed


def should_allow_message_with_reason(
    event: AstrMessageEvent,
    cfg: Optional[GroupConfig],
    default_action: str,
) -> Tuple[bool, str]:
    if cfg is None:
        action = str(default_action).lower()
        allowed = action != "silent"
        reason = "cfg_absent_default_allow" if allowed else "cfg_absent_default_silent"
        return allowed, reason

    # 配置存在但未启用时，按“关闭过滤”处理，直接放行。
    if not cfg.enabled:
        return True, "cfg_disabled"

    user_id = get_user_id(event)
    blacklist_enabled = bool(cfg.blacklist)
    whitelist_enabled = bool(cfg.whitelist)

    # 黑名单留空即禁用（不参与拦截）
    if blacklist_enabled and user_id and user_id in set(cfg.blacklist):
        return False, f"blacklist_hit user_id={user_id}"

    # 白名单留空即禁用（不要求白名单命中）
    if whitelist_enabled and (not user_id or user_id not in set(cfg.whitelist)):
        return False, f"whitelist_miss user_id={user_id or '<empty>'}"

    text = get_text(event)
    wake_hit, wake_reason = check_multi_wake_conditions_with_reason(
        event,
        text,
        cfg.wake_mode,
        cfg.wake_rules,
        cfg.wake_type,
        cfg.wake_value,
    )
    if wake_hit:
        return True, f"wake_hit {wake_reason}"
    return False, f"wake_miss {wake_reason}"


def check_multi_wake_conditions(
    event: AstrMessageEvent,
    text: str,
    wake_mode: str,
    wake_rules: List[Dict[str, Any]],
    fallback_wake_type: str,
    fallback_wake_value: str,
) -> bool:
    hit, _ = check_multi_wake_conditions_with_reason(
        event,
        text,
        wake_mode,
        wake_rules,
        fallback_wake_type,
        fallback_wake_value,
    )
    return hit


def check_multi_wake_conditions_with_reason(
    event: AstrMessageEvent,
    text: str,
    wake_mode: str,
    wake_rules: List[Dict[str, Any]],
    fallback_wake_type: str,
    fallback_wake_value: str,
) -> Tuple[bool, str]:
    rules = wake_rules if isinstance(wake_rules, list) else []
    if not rules:
        hit = check_wake_condition(event, text, fallback_wake_type, fallback_wake_value)
        return hit, f"fallback type={fallback_wake_type} hit={hit}"

    has_group_structure = any(isinstance(item, dict) and ("rules" in item or "group_mode" in item or "mode" in item) for item in rules)
    if has_group_structure:
        group_results: List[bool] = []
        group_parts: List[str] = []
        for idx, item in enumerate([x for x in rules if isinstance(x, dict)]):
            group_mode = str(item.get("group_mode", item.get("mode", "any")) or "any").strip().lower()
            if group_mode not in {"any", "all"}:
                group_mode = "any"
            raw_rules = item.get("rules", []) if isinstance(item.get("rules", []), list) else []
            rule_results = [_evaluate_rule_entry(event, text, rr) for rr in raw_rules if isinstance(rr, dict)]
            group_hit = all(rule_results) if group_mode == "all" else any(rule_results)
            group_results.append(group_hit)
            group_parts.append(f"G{idx + 1}({group_mode})={group_hit} rules={rule_results}")

        if not group_results:
            hit = check_wake_condition(event, text, fallback_wake_type, fallback_wake_value)
            return hit, f"empty_groups fallback type={fallback_wake_type} hit={hit}"

        final_hit = any(group_results)
        return final_hit, "; ".join(group_parts)

    legacy_results = [_evaluate_rule_entry(event, text, item) for item in rules if isinstance(item, dict)]
    if not legacy_results:
        hit = check_wake_condition(event, text, fallback_wake_type, fallback_wake_value)
        return hit, f"empty_legacy_rules fallback type={fallback_wake_type} hit={hit}"

    mode = str(wake_mode or "any").strip().lower()
    if mode == "all":
        final_hit = all(legacy_results)
    else:
        final_hit = any(legacy_results)
    return final_hit, f"legacy mode={mode} rules={legacy_results}"


def is_group_message(event: AstrMessageEvent) -> bool:
    def _looks_like_group(v: Any) -> bool:
        s = str(v or "").strip().lower()
        if not s:
            return False
        # 兼容常见格式: group / groupmessage / group_message / EventMessageType.GROUP_MESSAGE
        return (
            s == "group"
            or "groupmessage" in s
            or "group_message" in s
            or s.endswith(".group")
        )

    if hasattr(event, "is_group") and callable(getattr(event, "is_group")):
        try:
            return bool(event.is_group())
        except Exception:
            pass

    if hasattr(event, "message_type"):
        try:
            if _looks_like_group(getattr(event, "message_type")):
                return True
        except Exception:
            pass

    if hasattr(event, "get_message_type") and callable(getattr(event, "get_message_type")):
        try:
            if _looks_like_group(event.get_message_type()):
                return True
        except Exception:
            pass

    # 兼容 AstrBot 官方结构: event.message_obj.type
    msg_obj = getattr(event, "message_obj", None)
    if msg_obj is not None:
        try:
            if _looks_like_group(getattr(msg_obj, "type", None)):
                return True
        except Exception:
            pass

    return False


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
    direct = get_string_from_event(event, ["group_id"], ["get_group_id"]) or ""
    if direct:
        return direct

    # 兼容 AstrBot 官方事件结构: event.message_obj.group_id / event.message_obj.session_id
    msg_obj = getattr(event, "message_obj", None)
    if msg_obj is not None:
        for key in ("group_id", "session_id"):
            try:
                val = getattr(msg_obj, key, None)
                if val is not None and str(val).strip():
                    return str(val).strip()
            except Exception:
                pass

    return ""


def build_group_id_candidates(raw_group_id: str) -> List[str]:
    raw = str(raw_group_id or "").strip()
    if not raw:
        return []

    candidates: List[str] = []

    def _push(val: str):
        s = str(val or "").strip()
        if s and s not in candidates:
            candidates.append(s)

    _push(raw)

    if raw.isdigit():
        return candidates

    # 常见适配器格式: group_123456 / group:123456 / group-123456 / grp123456
    lower = raw.lower()
    prefix_patterns = [
        r"^(group|grp|g)[_:\-]([0-9]{4,})$",
        r"^(group|grp|g)([0-9]{4,})$",
    ]
    for pat in prefix_patterns:
        m = re.match(pat, lower)
        if m:
            _push(m.group(2))

    return candidates


def get_user_id(event: AstrMessageEvent) -> str:
    # In current QQ-focused usage, this returned value is treated as QQ number (string).
    direct = get_string_from_event(
        event,
        ["sender_id", "user_id", "qq"],
        ["get_sender_id", "get_user_id"],
    ) or ""
    if direct:
        return direct

    # 兼容 AstrBot 官方事件结构: event.message_obj.sender.user_id
    msg_obj = getattr(event, "message_obj", None)
    if msg_obj is not None:
        sender = getattr(msg_obj, "sender", None)
        if sender is not None:
            for key in ("user_id", "id", "qq"):
                try:
                    val = getattr(sender, key, None)
                    if val is not None and str(val).strip():
                        return str(val).strip()
                except Exception:
                    pass

    return ""


def get_self_id(event: AstrMessageEvent) -> str:
    return get_string_from_event(
        event,
        ["self_id", "bot_id"],
        ["get_self_id", "get_bot_id"],
    ) or ""


def get_text(event: AstrMessageEvent) -> str:
    def _to_text_from_message_like(obj: Any) -> str:
        if obj is None:
            return ""

        if isinstance(obj, str):
            return obj

        if isinstance(obj, (list, tuple)):
            parts: List[str] = []
            for seg in obj:
                if seg is None:
                    continue
                if isinstance(seg, str):
                    parts.append(seg)
                    continue

                # 常见结构1: segment.text / segment.content
                for key in ("text", "content"):
                    try:
                        val = getattr(seg, key, None)
                        if callable(val):
                            val = val()
                        if val is not None and str(val):
                            parts.append(str(val))
                            break
                    except Exception:
                        pass
                else:
                    # 常见结构2: segment.data = {"text": "..."}
                    try:
                        data = getattr(seg, "data", None)
                        if isinstance(data, dict):
                            txt = data.get("text") or data.get("content")
                            if txt is not None and str(txt):
                                parts.append(str(txt))
                    except Exception:
                        pass
            return "".join(parts)

        return ""

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

    # 兼容部分适配器: event.raw_message / event.text / event.content
    for key in ("raw_message", "text", "content"):
        if hasattr(event, key):
            try:
                v = getattr(event, key)
                if callable(v):
                    v = v()
                if v is not None and str(v):
                    return str(v)
            except Exception:
                pass

    # 兼容部分适配器: event.message 为消息段数组
    if hasattr(event, "message"):
        try:
            txt = _to_text_from_message_like(getattr(event, "message"))
            if txt:
                return txt
        except Exception:
            pass

    # 兼容 AstrBot 官方结构: event.message_obj.message_str
    msg_obj = getattr(event, "message_obj", None)
    if msg_obj is not None:
        try:
            val = getattr(msg_obj, "message_str", "")
            if val is not None:
                s = str(val)
                if s:
                    return s
        except Exception:
            pass

        # 兼容 message_obj 的其他文本字段
        for key in ("raw_message", "text", "content"):
            try:
                v = getattr(msg_obj, key, None)
                if callable(v):
                    v = v()
                if v is not None and str(v):
                    return str(v)
            except Exception:
                pass

        # 兼容 message_obj.message 为消息段数组
        try:
            txt = _to_text_from_message_like(getattr(msg_obj, "message", None))
            if txt:
                return txt
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
    logger.warning("[multi_filter] interrupt_result fallback failed: MessageEventResult has no callable interrupt/stop/block")
    return MessageEventResult().stop_event()


def is_management_command(text: str) -> bool:
    t = (text or "").strip().lower().lstrip("/")
    return (
        t.startswith("开启过滤器管理")
        or t.startswith("关闭过滤器管理")
        or t.startswith("过滤器管理状态")
        or t.startswith("设置过滤器管理端口")
    )


def extract_port_from_text(text: str) -> Optional[int]:
    # 只提取独立数字端口，避免误从其他字符串中抓取子串。
    m = re.search(r"(?<![./\d])(\d{1,5})(?!\d)", text or "")
    if not m:
        return None
    port = int(m.group(1))
    if 1 <= port <= 65535:
        return port
    return None
