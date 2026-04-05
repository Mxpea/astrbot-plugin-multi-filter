import sys

content = """import html
from typing import List, Dict, Any

def esc(s: str) -> str:
    return html.escape(str(s)) if s else ''

def render_admin_page(groups: List[Dict[str, Any]], settings: Dict[str, Any], msg: str = '') -> str:
    msg_html = f"<div class='ok'><strong>提示:</strong> {esc(msg)}</div>" if msg else ""
    allow_external = bool((settings or {}).get("web_allow_external_access", False))
    access_chip = "已允许外网访问" if allow_external else "仅本机访问"
    access_chip_hint = "监听 0.0.0.0" if allow_external else "监听 127.0.0.1"
    
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

        wake_rules_text = esc("\\n".join(rule_lines))

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

        while len(visual_rules) < 4:
            visual_rules.append({"type": "", "value": ""})

        wake_val = esc(g.get("wake_value", ""))
        if isinstance(g.get("wake_value"), list): wake_val = esc(",".join(g["wake_value"]))
        
        wl = esc(",".join(g.get("whitelist", [])))
        bl = esc(",".join(g.get("blacklist", [])))
        wt = g.get("wake_type", "always")
        wm = g.get("wake_mode", "any")
        en = "checked" if g.get("enabled", True) else ""
        
        form_html = f'''
        <form method='POST' action='/?op=save' class='card group-card'>
            <div class='group-head'>
                <div style='display:flex; align-items:center; gap:12px; margin-bottom:8px;'>
                    <h3 style='margin:0;'>群过滤 (群号: {esc(g.get("group_id", ""))})</h3>
                </div>
                <div>
                     <label class='switch-wrap'>
                        <input type='checkbox' name='enabled' {en} class='switch-input'>
                        <span class='switch-slider'></span>
                        <span class='switch-label'>启用本群拦截</span>
                    </label>
                </div>
            </div>
            <div class='group-body'>
                <input type='hidden' name='group_id' value='{esc(g.get("group_id", ""))}'>
                
                <div class='form-grid' style='margin-bottom:20px;'>
                    <div>
                        <label class='field-label'>白名单 <span class='hint'>(用户号，换行/逗号分隔，留空禁用)</span></label>
                        <textarea name='whitelist' rows='2' placeholder='如: 123456, 987654'>{wl}</textarea>
                    </div>
                    <div>
                        <label class='field-label'>黑名单 <span class='hint'>(用户号，换行/逗号分隔，留空禁用)</span></label>
                        <textarea name='blacklist' rows='2' placeholder='如: 111222'>{bl}</textarea>
                    </div>
                </div>
                
                <div class='rules-section'>
                    <div style='display:flex; gap:20px; margin-bottom:16px; flex-wrap:wrap;'>
                        <div>
                            <label class='field-label'>匹配模式</label>
                            <select name='wake_mode'>
                                <option value='any' {'selected' if wm=='any' else ''}>满足任意规则放行</option>
                                <option value='all' {'selected' if wm=='all' else ''}>满足所有规则放行</option>
                            </select>
                        </div>
                        <div>
                            <label class='field-label'>基础唤醒类型</label>
                            <select name='wake_type'>
                                <option value='always' {'selected' if wt=='always' else ''}>总是</option>
                                <option value='keyword' {'selected' if wt=='keyword' else ''}>关键字(包含)</option>
                                <option value='prefix' {'selected' if wt=='prefix' else ''}>前缀匹配</option>
                                <option value='mention' {'selected' if wt=='mention' else ''}>@机器人</option>
                                <option value='regex' {'selected' if wt=='regex' else ''}>正则表达式</option>
                            </select>
                        </div>
                        <div style='flex: 1; min-width: 200px;'>
                            <label class='field-label'>基础唤醒值</label>
                            <input type='text' name='wake_value' value='{wake_val}' placeholder='匹配内容，逗号分隔'>
                        </div>
                    </div>

                    <label class='field-label' style='margin-bottom:8px;'><strong>可视化多规则叠加（推荐）</strong> <span class='hint'>多条规则OR/AND</span></label>
                    <div style='overflow-x:auto; margin-bottom:16px;'>
                        <table class='rule-table'>
                            <thead>
                                <tr>
                                    <th width="60">规则</th>
                                    <th width="160">类型</th>
                                    <th>值 (逗号/换行/竖线分隔)</th>
                                </tr>
                            </thead>
                            <tbody>'''
                        
        for i in range(4):
            rt = visual_rules[i]['type']
            rv = esc(visual_rules[i]['value'])
            form_html += f'''
                                <tr>
                                    <td>#{i+1}</td>
                                    <td>
                                        <select name='rule_type_{i+1}'>
                                            <option value='' {'selected' if rt=='' else ''}>未启用</option>
                                            <option value='keyword' {'selected' if rt=='keyword' else ''}>关键字</option>
                                            <option value='prefix' {'selected' if rt=='prefix' else ''}>前缀</option>
                                            <option value='regex' {'selected' if rt=='regex' else ''}>正则</option>
                                            <option value='mention' {'selected' if rt=='mention' else ''}>@机器人</option>
                                            <option value='always' {'selected' if rt=='always' else ''}>总是</option>
                                        </select>
                                    </td>
                                    <td><input type='text' name='rule_value_{i+1}' value='{rv}' placeholder='值'></td>
                                </tr>'''

        form_html += f'''
                            </tbody>
                        </table>
                    </div>

                    <label class='field-label'>高级文本规则 <span class='hint'>(每行一条，格式 type:value)</span></label>
                    <textarea name='wake_rules_text' rows='3' placeholder='keyword:在吗\\nprefix:/'>{wake_rules_text}</textarea>
                </div>
                
                <div class='actions' style='margin-top:20px; border-top: 1px solid var(--border); padding-top:16px; display:flex; justify-content:space-between; align-items:center;'>
                    <button type='submit' class='btn-bg' style='color: white; background: var(--primary); border: none;'>
                        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                        保存设置
                    </button>
                    <button type='submit' formaction='/?op=delete' onclick='return confirm("确定删除吗？")' class='btn-outline' style='color: var(--danger); border: 1px solid var(--danger); background: transparent;'>
                        删除
                    </button>
                </div>
            </div>
        </form>
        '''
        rows_html += form_html

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>过滤器管理</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --surface: #ffffff;
            --border: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --danger-hover: #dc2626;
            --input-bg: #f8fafc;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            --hero-bg: #1e293b;
        }}

        [data-theme="dark"] {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #60a5fa;
            --input-bg: #0f172a;
            --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
            --hero-bg: #0f172a;
        }}

        * {{ box-sizing: border-box; transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease; }}
        body {{
            margin: 0; min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg); color: var(--text-main);
            padding: 24px 16px;
        }}

        .container {{ max-width: 900px; margin: 0 auto; }}

        /* Hero */
        .hero {{
            background: var(--hero-bg); border-radius: 16px; padding: 32px 24px;
            color: #ffffff; box-shadow: var(--shadow-md); margin-bottom: 24px;
            display: flex; justify-content: space-between; align-items: flex-start;
            position: relative; overflow: hidden;
        }}
        .hero::after {{ content: ""; position: absolute; right: -50px; bottom: -50px; width: 200px; height: 200px; background: rgba(59, 130, 246, 0.2); filter: blur(40px); border-radius: 50%; pointer-events: none; }}
        .hero h2 {{ margin: 0 0 12px 0; font-size: 24px; font-weight: 600; z-index: 1; position: relative; }}
        .hero p {{ margin: 0; color: rgba(255,255,255,0.7); font-size: 14px; max-width: 500px; z-index: 1; position: relative; line-height: 1.6; }}
        
        .chips {{ display: flex; gap: 8px; margin-top: 16px; z-index: 1; position: relative; }}
        .chip {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }}

        .theme-toggle {{
            background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: white;
            width: 40px; height: 40px; border-radius: 50%; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; z-index: 2; position: relative; backdrop-filter: blur(4px);
        }}
        .theme-toggle:hover {{ background: rgba(255,255,255,0.2); }}

        /* Cards */
        .card {{
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px; margin-bottom: 20px; box-shadow: var(--shadow-sm);
            overflow: hidden;
        }}
        .card-inner {{ padding: 20px; }}
        .group-head {{
            padding: 16px 20px; border-bottom: 1px solid var(--border);
            background: var(--bg); display: flex; justify-content: space-between;
            align-items: center; flex-wrap: wrap; gap: 12px;
        }}
        .group-body {{ padding: 20px; }}

        h3 {{ margin: 0 0 16px 0; font-size: 18px; font-weight: 600; color: var(--text-main); }}
        .field-label {{ display: block; font-size: 14px; font-weight: 500; margin-bottom: 8px; color: var(--text-main); }}
        .hint {{ font-weight: 400; font-size: 12px; color: var(--text-muted); margin-left: 4px; }}

        /* Forms */
        .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }}
        input[type="text"], input[type="password"], textarea, select {{
            width: 100%; padding: 10px 12px; border: 1px solid var(--border);
            background: var(--input-bg); color: var(--text-main);
            border-radius: 8px; font-size: 14px; outline: none; font-family: inherit; line-height: 1.5;
        }}
        input:focus, textarea:focus, select:focus {{ border-color: var(--primary); box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15); }}
        input[type="file"] {{ padding: 6px; font-size: 13px; cursor: pointer; }}

        .rules-section {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
        
        .rule-table {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
        .rule-table th {{ text-align: left; padding: 0 8px 12px 0; color: var(--text-muted); font-size: 13px; font-weight: 500; border-bottom: 1px solid var(--border); }}
        .rule-table td {{ padding: 12px 8px 0 0; vertical-align: top; }}
        .rule-table input, .rule-table select {{ padding: 8px 10px; font-size: 13px; border-radius: 6px; }}

        /* Buttons */
        .btn-bg, .btn-outline {{
            display: inline-flex; align-items: center; justify-content: center; gap: 8px;
            padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 500;
            cursor: pointer; text-decoration: none; transition: transform 0.1s, opacity 0.2s;
        }}
        .btn-bg:hover {{ opacity: 0.9; transform: translateY(-1px); }}
        .btn-outline:hover {{ background: var(--bg) !important; }}

        /* Status & Switch */
        .alert {{ padding: 14px; border-radius: 8px; margin-bottom: 24px; font-size: 14px; font-weight: 500; background: rgba(16, 185, 129, 0.1); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.2); display: flex; align-items: center; gap: 8px; }}

        .switch-wrap {{ display: flex; align-items: center; cursor: pointer; gap: 10px; user-select: none; }}
        .switch-input {{ display: none; }}
        .switch-slider {{ width: 36px; height: 20px; background-color: var(--border); border-radius: 20px; position: relative; transition: 0.2s; }}
        .switch-slider::before {{ content: ""; position: absolute; width: 16px; height: 16px; border-radius: 50%; background-color: white; top: 2px; left: 2px; transition: 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }}
        .switch-input:checked + .switch-slider {{ background-color: var(--success); }}
        .switch-input:checked + .switch-slider::before {{ transform: translateX(16px); }}
        .switch-label {{ font-size: 14px; font-weight: 500; color: var(--text-main); }}

        /* Utils */
        .header-actions {{ display: flex; gap: 12px; margin-top: 32px; margin-bottom: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
    </style>
</head>
<body>
    <div class='container'>
        <div class='hero'>
            <div>
                <h2>群组过滤器控制台</h2>
                <p>高级多条件组合过滤，支持正则表达式匹配以及跨设备导入导出备份配置。</p>
                <div class='chips'>
                    <span class='chip'>{esc(access_chip_hint)}</span>
                    <span class='chip'>支持任意或全部匹配</span>
                </div>
            </div>
            <button class='theme-toggle' id='themeBtn' title='切换深色/浅色' onclick='toggleTheme()'>🌙</button>
        </div>

        {f"<div class='alert'>{esc(msg)}</div>" if msg else ""}

        <div class='form-grid' style='gap: 24px;'>
            <div class='card' style='margin-bottom:0;'>
                <div class='card-inner'>
                    <h3>添加新拦截规则</h3>
                    <form method='POST' action='/?op=add' style='display:flex; gap:12px; align-items:flex-end;'>
                        <div style='flex:1;'>
                            <label class='field-label'>群号 (ID)</label>
                            <input type='text' name='group_id' placeholder='填入目标群号' required>
                        </div>
                        <button class='btn-bg' type='submit' style='background: var(--success); color: white; border: none;'>新增配置</button>
                    </form>
                </div>
            </div>

            <div class='card' style='margin-bottom:0;'>
                <div class='card-inner'>
                    <h3>配置备份</h3>
                    <form method='POST' action='/?op=import' enctype='multipart/form-data'>
                        <div style='display:flex; gap:12px; align-items:flex-end; margin-bottom:8px;'>
                            <div style='flex:1;'>
                                <label class='field-label'>导入还原 JSON</label>
                                <input type='file' name='import_file' accept='.json,application/json' style='width:100%; border: 1px dashed var(--text-muted);'>
                            </div>
                            <button class='btn-outline' type='submit' style='border: 1px solid var(--primary); color: var(--primary); background: transparent; padding: 7px 12px;'>导入</button>
                        </div>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <label style='font-size:13px; color:var(--text-muted); cursor:pointer; display:flex; align-items:center; gap:4px;'>
                                <input type='checkbox' name='replace_existing'> 导入时覆盖
                            </label>
                            <a href='/?op=export' style='font-size:13px; color:var(--primary); text-decoration:none;'>导出当前所有配置</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class='header-actions'>
            <h3 style='margin:0;'>活动群组 ({len(groups)})</h3>
        </div>

        {rows_html if groups else '<div class="card"><div style="text-align:center; padding: 60px 0; color: var(--text-muted);">暂无活动配置，请上方新增</div></div>'}

    </div>

    <script>
        const themeBtn = document.getElementById('themeBtn');
        const root = document.documentElement;
        
        function updateBtnIcon() {{
            themeBtn.innerText = root.hasAttribute('data-theme') ? '☀️' : '🌙';
        }}

        function setTheme(theme) {{
            if (theme === 'dark') {{
                root.setAttribute('data-theme', 'dark');
                localStorage.setItem('mf_theme', 'dark');
            }} else {{
                root.removeAttribute('data-theme');
                localStorage.setItem('mf_theme', 'light');
            }}
            updateBtnIcon();
        }}

        function toggleTheme() {{
            setTheme(root.hasAttribute('data-theme') ? 'light' : 'dark');
        }}

        const saved = localStorage.getItem('mf_theme');
        if (saved) {{
            setTheme(saved);
        }} else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {{
            setTheme('dark');
        }} else {{
            updateBtnIcon();
        }}
    </script>
</body>
</html>
'''
"""

with open("f:/WORKSPACE/astrbot-plugin-multi-filter/multi_filter/admin_page.py", "w", encoding="utf-8") as f:
    f.write(content)
print("File updated directly via python.")
