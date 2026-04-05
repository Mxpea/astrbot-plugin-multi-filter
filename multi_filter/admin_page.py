import html
from typing import List, Dict, Any

def esc(s: str) -> str:
    return html.escape(str(s)) if s else ''

def render_admin_page(groups: List[Dict[str, Any]], token: str, msg: str = '') -> str:
    msg_html = f"<div class='ok'><strong>提示:</strong> {esc(msg)}</div>" if msg else ""
    
    rows_html = ""
    for g in groups:
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

        # 单条且等价于基础 wake_type/wake_value 时，不回填到高级规则输入框，避免覆盖基础设置。
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

        wake_val = esc(g.get("wake_value", ""))
        if isinstance(g.get("wake_value"), list): wake_val = esc(",".join(g["wake_value"]))
        
        wl = esc(",".join(g.get("whitelist", [])))
        bl = esc(",".join(g.get("blacklist", [])))
        wt = g.get("wake_type", "always")
        wm = g.get("wake_mode", "any")
        en = "checked" if g.get("enabled", True) else ""
        
        form_html = f"""
        <form method='POST' action='/?token={esc(token)}&amp;op=save' style='border:1px solid #ccc; padding:15px; margin-bottom:15px; border-radius:5px;'>
            <h3 style='margin-top:0;'>群设置 (群号: {esc(g.get("group_id", ""))})</h3>
            <input type='hidden' name='group_id' value='{esc(g.get("group_id", ""))}'>
            <label><input type='checkbox' name='enabled' {en}> 启用此群过滤器</label><br><br>
            
            <label>白名单(用户号，逗号/分号/换行分隔；留空=禁用白名单限制):<br><textarea name='whitelist' rows='2' style='width:100%'>{wl}</textarea></label><br><br>
            <label>黑名单(用户号，逗号/分号/换行分隔；留空=禁用黑名单):<br><textarea name='blacklist' rows='2' style='width:100%'>{bl}</textarea></label><br><br>
            
            <label>唤醒类型: 
                <select name='wake_type'>
                    <option value='always' {'selected' if wt=='always' else ''}>总是</option>
                    <option value='keyword' {'selected' if wt=='keyword' else ''}>关键字(包含)</option>
                    <option value='prefix' {'selected' if wt=='prefix' else ''}>前缀匹配</option>
                    <option value='mention' {'selected' if wt=='mention' else ''}>@机器人</option>
                    <option value='regex' {'selected' if wt=='regex' else ''}>正则表达式</option>
                </select>
            </label> &nbsp;&nbsp;
            
            <label>多规则匹配模式:
                <select name='wake_mode'>
                    <option value='any' {'selected' if wm=='any' else ''}>满足任意规则 (OR)</option>
                    <option value='all' {'selected' if wm=='all' else ''}>满足所有规则 (AND)</option>
                </select>
            </label><br><br>
            
            <label>唤醒值(支持逗号/分号/竖线/换行分隔；mention/always 可留空):<br><input type='text' name='wake_value' value='{wake_val}' style='width:100%'></label><br><br>

            <label>高级唤醒规则(可选，每行一条，格式 type:value):
                <br><textarea name='wake_rules_text' rows='6' style='width:100%' placeholder='keyword:在吗,你好\nprefix:/\nregex:^/(help|menu)$\nmention:\nkeyword|regex:早上好,^早\\w+'>{wake_rules_text}</textarea>
            </label><br><br>
            <div style='font-size:12px; color:#666; line-height:1.6; background:#fafafa; border:1px dashed #ddd; padding:8px;'>
                <div>说明:</div>
                <div>1. type 支持 keyword/prefix/regex/mention/always，多个类型可用 | 连接（如 keyword|regex）。</div>
                <div>2. value 支持多个值，分隔符支持: 逗号、分号、竖线、换行。</div>
                <div>3. 多规则匹配模式 any=任意一条命中放行，all=全部命中放行。</div>
            </div><br>
            
            <hr style='border: none; border-top: 1px dotted #ccc;'/>
            <button type='submit' style='padding:5px 15px; background: #007bff; color: white; border: none; cursor:pointer;'>保存此群修改</button>
            <button type='submit' formaction='/?token={esc(token)}&amp;op=delete' onclick='return confirm("确定删除吗？")' style='padding:5px 15px; background: transparent; border:1px solid red; color:red; cursor:pointer; float:right;'>删除此群配置</button>
        </form>
        """
        rows_html += form_html

    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>过滤器管理</title>
    <style>
        body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 20px; max-width: 980px; background: #f5f7fb; color: #1f2937; }}
        .card {{ background: #fff; padding: 18px; border-radius: 10px; box-shadow: 0 2px 10px rgba(31,41,55,0.08); margin-bottom: 14px; }}
        .hint {{ font-size: 12px; color: #6b7280; line-height: 1.6; }}
        .ok {{ background:#ecfdf5; color:#065f46; padding:10px; margin-bottom:10px; border-radius:8px; border:1px solid #a7f3d0; }}
        textarea, input[type=text], select {{ width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; }}
        select {{ width: auto; min-width: 180px; }}
        .row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        .actions {{ display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }}
        button {{ padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; }}
        .btn-primary {{ background: #2563eb; color: #fff; }}
        .btn-green {{ background: #16a34a; color: #fff; }}
        .btn-danger {{ background: #fff; color: #dc2626; border: 1px solid #dc2626; }}
    </style>
</head>
<body>
    <div class='card'>
        <h2 style='margin-top:0'>AstrBot 群聊过滤器管理</h2>
        <p class='hint'>匹配规则完整支持: always / keyword / prefix / mention / regex；支持多规则 any/all。</p>
        {msg_html}
        <div class='ok'>
            <div><strong>持久化说明</strong></div>
            <div>配置和数据库会写入 AstrBot 用户目录，更新插件不会清空历史配置。</div>
        </div>
    </div>

    <div class='card'>
        <h3 style='margin-top:0'>新增群配置</h3>
        <form method='POST' action='/?token={esc(token)}&amp;op=add' class='row'>
            <input type='text' name='group_id' placeholder='填入群号 / group_id' required>
            <button class='btn-green' type='submit'>新增</button>
        </form>
    </div>

    {rows_html if groups else '<div class="card"><p>暂无群配置，请先新增。</p></div>'}

    <div class='card'>
        <h3 style='margin-top:0'>规则速查</h3>
        <div class='hint'>always: 总是命中（无需值）</div>
        <div class='hint'>keyword: 文本包含关键词（值支持逗号/分号/换行）</div>
        <div class='hint'>prefix: 文本前缀匹配（值可多个）</div>
        <div class='hint'>mention: @机器人（无需值）</div>
        <div class='hint'>regex: 正则匹配（建议一行一个正则，避免误分隔）</div>
    </div>
</body>
</html>
"""
