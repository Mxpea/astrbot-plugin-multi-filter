import html
from typing import List, Dict, Any

def esc(s: str) -> str:
    return html.escape(str(s)) if s else ''

def render_admin_page(groups: List[Dict[str, Any]], token: str, msg: str = '') -> str:
    msg_html = f"<div style='background:#d4edda;color:#155724;padding:10px;margin-bottom:10px;border-radius:4px;'>{esc(msg)}</div>" if msg else ""
    
    rows_html = ""
    for g in groups:
        rules = g.get("wake_rules", [])
        rule_lines = []
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
            
            <label>白名单(由于逗号分隔):<br><textarea name='whitelist' rows='2' style='width:100%'>{wl}</textarea></label><br><br>
            <label>黑名单(由于逗号分隔):<br><textarea name='blacklist' rows='2' style='width:100%'>{bl}</textarea></label><br><br>
            
            <label>唤醒类型: 
                <select name='wake_type'>
                    <option value='always' {'selected' if wt=='always' else ''}>总是</option>
                    <option value='keyword' {'selected' if wt=='keyword' else ''}>关键字(包含)</option>
                    <option value='regex' {'selected' if wt=='regex' else ''}>正则表达式</option>
                </select>
            </label> &nbsp;&nbsp;
            
            <label>多规则匹配模式:
                <select name='wake_mode'>
                    <option value='any' {'selected' if wm=='any' else ''}>满足任意规则 (OR)</option>
                    <option value='all' {'selected' if wm=='all' else ''}>满足所有规则 (AND)</option>
                </select>
            </label><br><br>
            
            <label>唤醒值(支持逗号多关键字或单条正则):<br><input type='text' name='wake_value' value='{wake_val}' style='width:100%'></label><br><br>

            <label>高级唤醒规则(可选，每行一条，格式 type:value；type 可写 keyword/prefix/regex/mention/always；value 可写多个用逗号分隔):
                <br><textarea name='wake_rules_text' rows='4' style='width:100%' placeholder='keyword:在吗,你好\nregex:^/\nmention:'>{wake_rules_text}</textarea>
            </label><br><br>
            
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
</head>
<body style='font-family: Arial, sans-serif; margin: 20px; max-width: 800px; background: #f9f9f9;'>
    <div style='background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>
        <h2 style='margin-top:0'>AstrBot 群聊过滤器管理 (安全模式/纯HTML版)</h2>
        <p style='color: #666;'>此版本全面兼容任何环境，解决了由于缓存或浏览器的兼容性导致的无响应问题。</p>
        {msg_html}
        
        <div style='border:1px dashed #007bff; padding:15px; margin-bottom:20px; border-radius:5px; background: #eef8ff;'>
            <h3 style='margin-top:0'>新增群配置</h3>
            <form method='POST' action='/?token={esc(token)}&amp;op=add'>
                <input type='text' name='group_id' placeholder='填入群号 / group_id' required style='padding:5px;'>
                <button type='submit' style='padding:5px 10px; background: #28a745; color: white; border: none; cursor:pointer;'>增加</button>
            </form>
        </div>
        
        <hr style='border: none; border-top: 2px solid #eee; margin: 30px 0;'/>
        
        {rows_html if groups else '<p>暂无群配置，请在上方新增。</p>'}
    </div>
</body>
</html>
"""
