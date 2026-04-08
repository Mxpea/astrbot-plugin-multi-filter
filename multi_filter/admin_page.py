import html
import json
from pathlib import Path
from typing import List, Dict, Any

VALID_RULE_TYPES = {"keyword", "prefix", "regex", "mention", "always"}

def esc(s: str) -> str:
    return html.escape(str(s)) if s else ''


_ADMIN_PAGE_TEMPLATE_PATH = Path(__file__).with_name("admin_page.template.html")


def _load_admin_page_template() -> str:
    return _ADMIN_PAGE_TEMPLATE_PATH.read_text(encoding="utf-8")


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


def _normalize_rule_groups_for_ui(g: Dict[str, Any]) -> List[Dict[str, Any]]:
    wake_mode = str(g.get("wake_mode", "any") or "any").strip().lower()
    if wake_mode not in {"any", "all"}:
        wake_mode = "any"

    raw_groups = g.get("wake_rules", [])
    if isinstance(raw_groups, list) and any(isinstance(item, dict) and ("rules" in item or "group_mode" in item or "mode" in item) for item in raw_groups):
        normalized_groups: List[Dict[str, Any]] = []
        for group in raw_groups:
            if not isinstance(group, dict):
                continue
            group_mode = str(group.get("group_mode", group.get("mode", "any")) or "any").strip().lower()
            if group_mode not in {"any", "all"}:
                group_mode = "any"
            rules: List[Dict[str, Any]] = []
            for raw_rule in group.get("rules", []) if isinstance(group.get("rules", []), list) else []:
                rule = _normalize_rule_item(raw_rule)
                if rule is not None:
                    rules.append(rule)
            if rules:
                normalized_groups.append({"group_mode": group_mode, "rules": rules})
        if normalized_groups:
            return normalized_groups

    flat_rules: List[Dict[str, Any]] = []
    if isinstance(raw_groups, list):
        for item in raw_groups:
            rule = _normalize_rule_item(item)
            if rule is not None:
                flat_rules.append(rule)

    if flat_rules:
        return [{"group_mode": wake_mode, "rules": flat_rules}]

    wake_type = str(g.get("wake_type", "always") or "always").strip().lower()
    wake_value = g.get("wake_value", "")
    if wake_type == "keyword":
        if isinstance(wake_value, list):
            value = [str(x).strip() for x in wake_value if str(x).strip()]
        else:
            try:
                parsed = json.loads(str(wake_value or ""))
                value = [str(x).strip() for x in parsed if str(x).strip()] if isinstance(parsed, list) else [x.strip() for x in str(wake_value or "").split(",") if x.strip()]
            except Exception:
                value = [x.strip() for x in str(wake_value or "").split(",") if x.strip()]
    elif wake_type in {"prefix", "regex"}:
        value = str(wake_value or "")
    else:
        value = ""

    return [{"group_mode": wake_mode, "rules": [{"type": wake_type, "value": value, "invert": False}]}]

def render_admin_page(groups: List[Dict[str, Any]], settings: Dict[str, Any], msg: str = '') -> str:
    msg_html = f"<div class='alert ok'><strong>提示:</strong> {esc(msg)}</div>" if msg else ""
    allow_external = bool((settings or {}).get("web_allow_external_access", False))
    access_chip = "已允许外网访问" if allow_external else "仅本机访问"
    access_chip_hint = "监听 0.0.0.0" if allow_external else "监听 127.0.0.1"

    default_group_id = "__default__"
    normal_groups: List[Dict[str, Any]] = []
    default_group: Dict[str, Any] = {
        "group_id": default_group_id,
        "enabled": False,
        "whitelist": [],
        "blacklist": [],
        "wake_type": "always",
        "wake_value": "",
        "wake_mode": "any",
        "wake_rules": [],
    }
    for g in groups:
        if str(g.get("group_id", "")).strip() == default_group_id:
            default_group = g
        else:
            normal_groups.append(g)

    def render_rule_card(g: Dict[str, Any], *, is_default: bool = False) -> str:
        rules = g.get("wake_rules", [])
        rule_lines = []
        wt = str(g.get("wake_type", "always") or "always")
        raw_wv = g.get("wake_value", "")
        if isinstance(raw_wv, list):
            wv_norm = [str(x).strip() for x in raw_wv if str(x).strip()]
        else:
            wv_norm = str(raw_wv or "").strip()

        if isinstance(rules, list):
            for item in rules:
                if not isinstance(item, dict):
                    continue
                t = str(item.get("type", "")).strip()
                v = item.get("value", "")
                if isinstance(v, list):
                    v = ",".join([str(x).strip() for x in v if str(x).strip()])
                else:
                    v = str(v or "")
                if t:
                    rule_lines.append(f"{t}:{v}")

        if isinstance(rules, list) and len(rules) == 1:
            only = rules[0] if isinstance(rules[0], dict) else None
            if isinstance(only, dict):
                rt = str(only.get("type", "")).strip().lower()
                rv = only.get("value", "")
                if isinstance(rv, list):
                    rv_norm = [str(x).strip() for x in rv if str(x).strip()]
                else:
                    rv_norm = str(rv or "").strip()

                if rt == wt.strip().lower() and rv_norm == wv_norm:
                    rule_lines = []

        wake_rules_text = esc("\n".join(rule_lines))

        visual_rules: List[Dict[str, str]] = []
        if isinstance(rules, list):
            for item in rules:
                if not isinstance(item, dict):
                    continue
                rt = str(item.get("type", "") or "").strip().lower()
                rv_any = item.get("value", "")
                if isinstance(rv_any, list):
                    rv = ",".join([str(x).strip() for x in rv_any if str(x).strip()])
                else:
                    rv = str(rv_any or "")
                if rt:
                    visual_rules.append({"type": rt, "value": rv})
                if len(visual_rules) >= 4:
                    break

        if not visual_rules:
            visual_rules.append({"type": wt, "value": str(g.get("wake_value", "") or "")})

        wake_val = esc(g.get("wake_value", ""))
        if isinstance(g.get("wake_value"), list):
            wake_val = esc(",".join(g["wake_value"]))

        wl = esc(",".join(g.get("whitelist", [])))
        bl = esc(",".join(g.get("blacklist", [])))
        wt = g.get("wake_type", "always")
        wm = g.get("wake_mode", "any")
        en = "checked" if g.get("enabled", True) else ""

        gid = str(g.get("group_id", ""))
        safe_gid = esc(gid)
        title = "默认群配置（未单独配置的群）" if is_default else f"群配置（群号: {safe_gid}）"
        subtitle = "当群没有独立配置时，按此配置执行。" if is_default else "仅影响当前群。"
        rules_seed = esc(json.dumps(_normalize_rule_groups_for_ui(g), ensure_ascii=False))

        delete_html = ""
        if not is_default:
            delete_html = """
                    <button type='submit' formaction='/?op=delete' onclick='return confirm("确定删除此群配置吗？")' class='btn-outline danger'>删除此群配置</button>
            """

        form_html = f'''
        <form method='POST' action='/?op=save' class='card group-card config-form' data-group-id='{safe_gid}'>
            <div class='group-head'>
                <div>
                    <h3 style='margin:0;'>{title}</h3>
                    <div class='hint'>{subtitle}</div>
                </div>
                <label class='switch-wrap'>
                        <input type='checkbox' name='enabled' {en} class='switch-input rule-enabled'>
                        <span class='switch-slider'></span>
                        <span class='switch-label'>启用本配置</span>
                </label>
            </div>
            <div class='group-body'>
                <input type='hidden' name='group_id' value='{safe_gid}'>
                <input type='hidden' name='wake_type' value='{esc(wt)}' class='fallback-wake-type'>
                <input type='hidden' name='wake_value' value='{wake_val}' class='fallback-wake-value'>
                <input type='hidden' name='wake_rules_json' value='' class='wake-rules-json'>

                <div class='flow-note'>
                    执行顺序：黑名单拦截 → 白名单校验 → 触发条件判断。任一步未通过则不放行。
                </div>

                <section class='module'>
                    <div class='module-title'>一、用户过滤（先判断）</div>
                    <div class='priority-note'>优先级：黑名单 &gt; 白名单 &gt; 触发规则</div>
                    <div class='form-grid' style='margin-bottom:14px;'>
                    <div>
                        <label class='field-label'>允许名单（白名单） <span class='hint'>用户号，支持换行/逗号/分号；留空=不限制</span></label>
                        <textarea name='whitelist' rows='2' class='user-list whitelist' placeholder='示例：\n10001\n10002,10003'>{wl}</textarea>
                    </div>
                    <div>
                        <label class='field-label'>拒绝名单（黑名单） <span class='hint'>用户号，支持换行/逗号/分号；留空=不拦截</span></label>
                        <textarea name='blacklist' rows='2' class='user-list blacklist' placeholder='示例：\n20001\n20002,20003'>{bl}</textarea>
                    </div>
                </div>
                </section>

                <section class='module rules-section'>
                    <div class='module-title'>二、规则组（再判断）</div>
                    <div class='guide-card'>
                        每个规则组内部可设为 OR 或 AND；多个规则组之间按“任一组命中即触发”。规则行右侧可开启“反转条件”。
                    </div>

                    <input type='hidden' name='wake_mode' value='any' class='rules-join-mode'>

                    <div class='groups-builder' data-groups='{rules_seed}'>
                        <div class='groups-list'></div>
                        <button type='button' class='btn-outline add-group'>+ 添加规则组</button>
                    </div>

                    <div class='tester'>
                        <div class='module-title' style='margin-top:16px;'>三、规则测试（不保存）</div>
                        <div class='form-grid'>
                            <div>
                                <label class='field-label'>测试消息内容</label>
                                <input type='text' class='test-message' placeholder='输入一条消息，例如：/help'>
                            </div>
                            <div>
                                <label class='field-label'>附加条件</label>
                                <label class='hint' style='display:flex; gap:6px; align-items:center; margin-top:10px;'>
                                    <input type='checkbox' class='test-mentioned'> 视为“已@机器人”
                                </label>
                            </div>
                        </div>
                        <div style='margin-top:10px;'>
                            <button type='button' class='btn-outline run-test'>测试是否触发</button>
                            <span class='test-result hint'></span>
                        </div>
                    </div>
                </section>

                <section class='module'>
                    <details>
                        <summary><strong>高级规则（仅高级用户）</strong> <span class='hint'>不建议新手使用</span></summary>
                        <div class='hint' style='margin:8px 0;'>
                            适用场景：需要一次性粘贴历史规则或复杂正则。格式：每行 type:value，示例 keyword:早上好 或 regex:^/(help|menu)$。
                        </div>
                        <label class='field-label'>高级文本规则</label>
                        <textarea name='wake_rules_text' rows='4' placeholder='keyword:在吗,你好\nprefix:/\nregex:^/(help|menu)$'>{wake_rules_text}</textarea>
                    </details>
                </section>

                <div class='form-error hint'></div>

                <div class='actions' style='margin-top:18px; border-top: 1px solid var(--border); padding-top:14px; display:flex; justify-content:space-between; align-items:center;'>
                    <button type='submit' class='btn-bg primary'>
                        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                        保存配置
                    </button>
                    {delete_html}
                </div>
            </div>
        </form>
        '''
        return form_html

    normal_rows_html = "".join(render_rule_card(g, is_default=False) for g in normal_groups)
    default_row_html = render_rule_card(default_group, is_default=True)
    normal_rows_section = normal_rows_html if normal_groups else '<div class="card"><div style="text-align:center; padding: 60px 0; color: var(--text-muted);">暂无活动配置，请上方新增</div></div>'

    tpl = _load_admin_page_template()
    replacements = {
        "__MSG_HTML__": msg_html,
        "__ACCESS_CHIP_HINT__": esc(access_chip_hint),
        "__ACCESS_CHIP__": esc(access_chip),
        "__DEFAULT_ROW_HTML__": default_row_html,
        "__NORMAL_GROUP_COUNT__": str(len(normal_groups)),
        "__NORMAL_ROWS_SECTION__": normal_rows_section,
    }
    for token, value in replacements.items():
        tpl = tpl.replace(token, value)
    return tpl
