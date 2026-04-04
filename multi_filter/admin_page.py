ADMIN_HTML = """<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Multi Filter 管理页面</title>
  <style>
    :root {
      --bg: #f4f8fc;
      --panel: #ffffff;
      --fg: #1b2734;
      --muted: #6a7a8d;
      --line: #d8e3ee;
      --main: #0d86ff;
      --main-dark: #096bd1;
      --danger: #cf2f2f;
      --ok: #0e9b56;
      --warn: #c27a00;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--fg);
      font-family: \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif;
      background:
        radial-gradient(circle at 10% 8%, #ffffff 0, #f4f8fc 55%, #e9f1fa 100%),
        linear-gradient(135deg, #f8fbff, #edf4fb);
      min-height: 100vh;
    }
    .wrap { max-width: 1080px; margin: 24px auto; padding: 0 16px 40px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 10px 24px rgba(24, 49, 73, 0.08);
      padding: 18px;
      margin-bottom: 14px;
    }
    .title { margin: 0 0 8px; font-size: 24px; }
    .subtitle { margin: 0; color: var(--muted); font-size: 13px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
    .col { flex: 1 1 260px; min-width: 220px; }
    .col-sm { flex: 0 0 180px; }
    label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .hint { color: var(--muted); font-size: 12px; margin-top: 5px; line-height: 1.5; }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 9px;
      padding: 9px 10px;
      background: #fff;
      color: var(--fg);
      font-size: 14px;
      outline: none;
      transition: border-color .15s ease;
    }
    input:focus, select:focus, textarea:focus { border-color: var(--main); }
    textarea { min-height: 110px; resize: vertical; }
    .toolbar { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    button {
      border: none;
      border-radius: 9px;
      padding: 9px 14px;
      font-size: 14px;
      line-height: 1;
      cursor: pointer;
      background: var(--main);
      color: #fff;
      transition: background .15s ease, transform .15s ease;
    }
    button:hover { background: var(--main-dark); }
    button.secondary { background: #6e7f92; }
    button.secondary:hover { background: #596a7d; }
    button.danger { background: var(--danger); }
    button.danger:hover { background: #ad2323; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .split { display: grid; grid-template-columns: 1.2fr 1fr; gap: 14px; }
    .status {
      margin-top: 12px;
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 13px;
      border: 1px solid var(--line);
      background: #f9fbfe;
    }
    .status.ok { color: var(--ok); border-color: #b6e8cf; background: #f2fcf7; }
    .status.err { color: var(--danger); border-color: #f3c2c2; background: #fff5f5; }
    .status.warn { color: var(--warn); border-color: #f1d8a4; background: #fffaf0; }
    .kpi {
      display: inline-block;
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: #f8fbff;
      margin-right: 8px;
    }
    .rule-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 10px;
    }
    .rule-item {
      display: grid;
      grid-template-columns: 150px 1fr 44px;
      gap: 10px;
      align-items: start;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fbfdff;
    }
    .rule-item .rule-meta {
      font-size: 12px;
      color: var(--muted);
      margin-top: 4px;
      line-height: 1.5;
    }
    .rule-item .rule-value.disabled {
      opacity: 0.6;
      background: #f4f7fb;
    }
    .rule-remove {
      width: 36px;
      height: 36px;
      padding: 0;
      border-radius: 50%;
      font-size: 18px;
      line-height: 36px;
      text-align: center;
      background: #f4f7fb;
      color: var(--danger);
      border: 1px solid var(--line);
      align-self: end;
    }
    .rule-remove:hover { background: #fff0f0; }
    .section-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 12px;
    }
    .section-title h3 { margin: 0; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 999px;
      background: #eef6ff;
      color: #1766c2;
      font-size: 12px;
      border: 1px solid #d8e8fb;
    }
    @media (max-width: 900px) {
      .split { grid-template-columns: 1fr; }
      .col, .col-sm { min-width: 0; }
      .rule-item { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1 class=\"title\">Multi Filter 管理页面</h1>
      <p class=\"subtitle\">此页面使用 token 鉴权，建议仅在本机访问并定期轮换 token。</p>
        <div style="margin-top:12px;">
          <label>白名单（每行一个 QQ号）</label>
        <span class=\"kpi\" id=\"kpiPort\">端口: -</span>
          <div class="hint">当前按 QQ号 字符串匹配。保存时会自动去重并移除空行。</div>
      </div>
    </div>

          <label>黑名单（每行一个 QQ号，优先级高于白名单）</label>
      <div class=\"card\">
          <div class="hint">当前按 QQ号 字符串匹配。黑名单命中时将直接拦截，不再判断唤醒条件。</div>
          <h3>群规则管理</h3>
          <span class=\"pill\">黑名单优先</span>
        </div>
        <div class=\"row\">
          <div class=\"col\">
            <label>已配置群</label>
            <select id=\"groupSelect\"></select>
          </div>
          <div class=\"col\">
            <label>新增群号</label>
            <input id=\"newGroupId\" placeholder=\"例如 123456789\" />
          </div>
          <div class=\"col-sm\">
            <button id=\"addGroupBtn\">新增并加载</button>
          </div>
        </div>

        <div class=\"row\" style=\"margin-top:12px;\">
          <div class=\"col\">
            <label>群号</label>
            <input id=\"groupId\" readonly />
          </div>
          <div class=\"col\">
            <label>启用过滤</label>
            <select id=\"enabled\">
              <option value=\"1\">启用（按白名单 + 唤醒条件）</option>
              <option value=\"0\">禁用（该群全部放行）</option>
            </select>
          </div>
        </div>

        <div style=\"margin-top:12px;\">
          <label>白名单（每行一个用户 ID）</label>
          <textarea id=\"whitelist\" placeholder=\"10001&#10;10002\"></textarea>
          <div class=\"hint\">保存时会自动去重并移除空行。</div>
        </div>

        <div style=\"margin-top:12px;\">
          <label>黑名单（每行一个用户 ID，优先级高于白名单）</label>
          <textarea id=\"blacklist\" placeholder=\"20001&#10;20002\"></textarea>
          <div class=\"hint\">黑名单命中时将直接拦截，不再判断唤醒条件。</div>
        </div>

        <div class=\"row\" style=\"margin-top:12px;\">
          <div class=\"col\">
            <label>唤醒类型</label>
            <select id=\"wakeType\">
              <option value=\"always\">always</option>
              <option value=\"keyword\">keyword</option>
              <option value=\"prefix\">prefix</option>
              <option value=\"mention\">mention</option>
              <option value=\"regex\">regex</option>
            </select>
          </div>
          <div class=\"col\">
            <label>唤醒值</label>
            <input id=\"wakeValue\" />
            <div class=\"hint\" id=\"wakeHint\"></div>
          </div>
        </div>

        <div class=\"row\" style=\"margin-top:12px;\">
          <div class=\"col\">
            <label>多唤醒规则模式</label>
            <select id=\"wakeMode\">
              <option value=\"any\">any（任一规则命中即放行）</option>
              <option value=\"all\">all（全部规则命中才放行）</option>
            </select>
          </div>
          <div class=\"col\">
            <label>规则操作</label>
            <div class=\"toolbar\" style=\"margin-top:0;\">
              <button id=\"addWakeRuleBtn\">+ 新增规则</button>
              <button id=\"clearWakeRulesBtn\" class=\"secondary\">清空规则</button>
            </div>
          </div>
        </div>

        <div style=\"margin-top:12px;\">
          <label>多唤醒规则</label>
          <div class=\"hint\">建议先用“+ 新增规则”快速添加，再逐条选择规则类型、输入规则值。模式为 any 时命中任一条即放行；all 时必须全部命中。</div>
          <div class=\"hint\">快捷写法：keyword 规则支持逗号分隔多个关键词，mention / always 不需要填写值。</div>
          <div id=\"wakeRulesList\" class=\"rule-list\"></div>
        </div>

        <div class=\"toolbar\">
          <button id=\"saveBtn\">保存当前群配置</button>
          <button id=\"deleteBtn\" class=\"danger\">删除当前群配置</button>
          <button id=\"refreshBtn\" class=\"secondary\">刷新群列表</button>
        </div>
        <div id=\"groupStatus\" class=\"status\">准备就绪</div>
      </div>

      <div class=\"card\">
        <h3 style=\"margin:0 0 12px;\">全局设置</h3>
        <div class=\"row\">
          <div class=\"col\">
            <label>管理端口</label>
            <input id=\"settingPort\" type=\"number\" min=\"1\" max=\"65535\" />
          </div>
          <div class=\"col\">
            <label>自动启动管理页</label>
            <select id=\"settingAutoStart\">
              <option value=\"1\">开启</option>
              <option value=\"0\">关闭</option>
            </select>
          </div>
        </div>
        <div style=\"margin-top:12px;\">
          <label>管理 Token</label>
          <input id=\"settingToken\" type=\"text\" placeholder=\"请输入高强度 token\" />
        </div>
        <div class=\"toolbar\">
          <button id=\"saveSettingsBtn\">保存全局设置</button>
          <button id=\"copyUrlBtn\" class=\"secondary\">复制访问地址</button>
        </div>
        <div class=\"hint\" style=\"margin-top:8px;\">提示: 修改端口或 token 后，建议通过聊天命令重启管理页以立即生效。</div>
        <div id=\"settingsStatus\" class=\"status\">未加载</div>
      </div>
    </div>
  </div>

  <script>
    const token = new URLSearchParams(location.search).get("token") || "";
    const REQUEST_TIMEOUT_MS = 8000;
    const state = {
      groups: [],
      currentGroupId: "",
      loading: false,
    };

    const $ = (id) => document.getElementById(id);

    const el = {
      kpiGroups: $("kpiGroups"),
      kpiPort: $("kpiPort"),
      kpiAutoStart: $("kpiAutoStart"),
      groupSelect: $("groupSelect"),
      newGroupId: $("newGroupId"),
      groupId: $("groupId"),
      enabled: $("enabled"),
      whitelist: $("whitelist"),
      blacklist: $("blacklist"),
      wakeType: $("wakeType"),
      wakeValue: $("wakeValue"),
      wakeMode: $("wakeMode"),
      wakeRulesList: $("wakeRulesList"),
      addWakeRuleBtn: $("addWakeRuleBtn"),
      clearWakeRulesBtn: $("clearWakeRulesBtn"),
      wakeHint: $("wakeHint"),
      groupStatus: $("groupStatus"),
      addGroupBtn: $("addGroupBtn"),
      saveBtn: $("saveBtn"),
      deleteBtn: $("deleteBtn"),
      refreshBtn: $("refreshBtn"),
      settingPort: $("settingPort"),
      settingAutoStart: $("settingAutoStart"),
      settingToken: $("settingToken"),
      saveSettingsBtn: $("saveSettingsBtn"),
      copyUrlBtn: $("copyUrlBtn"),
      settingsStatus: $("settingsStatus"),
    };

    function setStatus(target, message, type) {
      target.textContent = message;
      target.className = "status " + (type || "");
    }

    function setBusy(busy) {
      state.loading = busy;
      [
        el.addGroupBtn,
        el.saveBtn,
        el.deleteBtn,
        el.refreshBtn,
        el.saveSettingsBtn,
        el.copyUrlBtn,
        el.addWakeRuleBtn,
        el.clearWakeRulesBtn,
      ].forEach((btn) => {
        btn.disabled = busy;
      });
    }

    async function api(path, options) {
      const sep = path.includes("?") ? "&" : "?";
      const url = path + sep + "token=" + encodeURIComponent(token);

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      try {
        const resp = await fetch(url, {
          headers: {
            "Content-Type": "application/json",
            "X-Token": token,
          },
          signal: controller.signal,
          ...options,
        });

        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.ok === false) {
          throw new Error(data.error || ("HTTP " + resp.status));
        }
        return data;
      } catch (err) {
        if (err && err.name === "AbortError") {
          throw new Error("请求超时，请检查插件状态或网络环境");
        }
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }

    function normalizeWhitelist(text) {
      const lines = (text || "")
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      return Array.from(new Set(lines));
    }

    function normalizeWakeRuleType(type) {
      const t = String(type || "").trim().toLowerCase();
      if (["always", "keyword", "prefix", "mention", "regex"].includes(t)) {
        return t;
      }
      return "keyword";
    }

    function wakeRuleHelpText(type) {
      const t = normalizeWakeRuleType(type);
      if (t === "keyword") return "关键词规则，支持逗号分隔多个关键词";
      if (t === "prefix") return "前缀匹配，例如 / 或 !";
      if (t === "mention") return "@ 机器人即可命中";
      if (t === "regex") return "正则匹配，建议先在本地测试";
      return "always 会让该条规则永远命中";
    }

    function ruleValueToDisplay(type, value) {
      const t = normalizeWakeRuleType(type);
      if (t === "keyword") {
        const keywords = Array.isArray(value) ? value : [];
        return keywords.join(",");
      }
      if (t === "prefix" || t === "regex") {
        return String(value || "");
      }
      return "";
    }

    function getWakeHint(wakeType) {
      if (wakeType === "always") return "always: 白名单内任何消息都放行。";
      if (wakeType === "keyword") return "keyword: 输入逗号分隔关键词，例如 帮助,查询,状态。";
      if (wakeType === "prefix") return "prefix: 仅当消息以指定前缀开头时放行，例如 /。";
      if (wakeType === "mention") return "mention: 仅当消息 @ 机器人时放行，此模式忽略唤醒值。";
      if (wakeType === "regex") return "regex: 使用正则表达式匹配消息，例如 ^/test\\b。";
      return "";
    }

    function updateWakeHint() {
      const wakeType = el.wakeType.value;
      el.wakeHint.textContent = getWakeHint(wakeType);

      if (wakeType === "mention" || wakeType === "always") {
        el.wakeValue.value = "";
        el.wakeValue.disabled = true;
        el.wakeValue.placeholder = "该模式不需要唤醒值";
      } else if (wakeType === "keyword") {
        el.wakeValue.disabled = false;
        el.wakeValue.placeholder = "例如: 帮助,查询,状态";
      } else if (wakeType === "prefix") {
        el.wakeValue.disabled = false;
        el.wakeValue.placeholder = "例如: /";
      } else {
        el.wakeValue.disabled = false;
        el.wakeValue.placeholder = "例如: ^/test\\b";
      }
    }

    function getCurrentAccessUrl() {
      const port = parseInt(el.settingPort.value || "0", 10) || 8010;
      const tk = (el.settingToken.value || token || "").trim();
      return "http://127.0.0.1:" + port + "/?token=" + encodeURIComponent(tk);
    }

    function refreshKpi() {
      el.kpiGroups.textContent = "已配置群: " + state.groups.length;
      el.kpiPort.textContent = "端口: " + (el.settingPort.value || "-");
      el.kpiAutoStart.textContent = "自启: " + (el.settingAutoStart.value === "1" ? "开启" : "关闭");
    }

    function createWakeRuleItem(rule) {
      const item = document.createElement("div");
      item.className = "rule-item";

      const left = document.createElement("div");
      const typeLabel = document.createElement("label");
      typeLabel.textContent = "规则类型";
      const typeSelect = document.createElement("select");
      ["keyword", "prefix", "mention", "regex", "always"].forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        typeSelect.appendChild(opt);
      });
      typeSelect.value = normalizeWakeRuleType(rule?.type || "keyword");
      const typeMeta = document.createElement("div");
      typeMeta.className = "rule-meta";
      left.appendChild(typeLabel);
      left.appendChild(typeSelect);
      left.appendChild(typeMeta);

      const middle = document.createElement("div");
      const valueLabel = document.createElement("label");
      valueLabel.textContent = "规则值";
      const valueInput = document.createElement("input");
      valueInput.className = "rule-value";
      valueInput.placeholder = "输入规则值";
      valueInput.value = ruleValueToDisplay(typeSelect.value, rule?.value);
      const valueMeta = document.createElement("div");
      valueMeta.className = "rule-meta";
      middle.appendChild(valueLabel);
      middle.appendChild(valueInput);
      middle.appendChild(valueMeta);

      const removeBtn = document.createElement("button");
      removeBtn.className = "rule-remove";
      removeBtn.type = "button";
      removeBtn.textContent = "×";
      removeBtn.title = "删除这条规则";

      function syncRuleUI() {
        const t = normalizeWakeRuleType(typeSelect.value);
        if (t === "mention" || t === "always") {
          valueInput.value = "";
          valueInput.disabled = true;
          valueInput.classList.add("disabled");
          valueInput.placeholder = "该规则不需要值";
        } else {
          valueInput.disabled = false;
          valueInput.classList.remove("disabled");
          if (t === "keyword") {
            valueInput.placeholder = "例如: 帮助,查询,状态";
          } else if (t === "prefix") {
            valueInput.placeholder = "例如: /";
          } else {
            valueInput.placeholder = "例如: ^/test\\b";
          }
        }
        typeMeta.textContent = wakeRuleHelpText(t);
        valueMeta.textContent = t === "keyword"
          ? "支持逗号分隔多个关键词"
          : t === "prefix"
            ? "前缀匹配，常用于命令前缀"
            : t === "regex"
              ? "正则匹配，建议先在本地测试"
              : t === "mention"
                ? "@ 机器人即可放行"
                : "任何消息都作为单条规则通过";
      }

      typeSelect.addEventListener("change", syncRuleUI);
      removeBtn.addEventListener("click", () => item.remove());

      item.appendChild(left);
      item.appendChild(middle);
      item.appendChild(removeBtn);
      syncRuleUI();
      return item;
    }

    function renderWakeRules(rules) {
      el.wakeRulesList.innerHTML = "";
      const list = Array.isArray(rules) && rules.length > 0 ? rules : [{ type: el.wakeType.value, value: "" }];
      list.forEach((rule) => {
        el.wakeRulesList.appendChild(createWakeRuleItem(rule));
      });
    }

    function addEmptyWakeRule() {
      const items = Array.from(el.wakeRulesList.querySelectorAll(".rule-item"));
      const defaultType = items.length > 0
        ? items[items.length - 1].querySelector("select").value
        : el.wakeType.value;
      el.wakeRulesList.appendChild(createWakeRuleItem({ type: defaultType, value: "" }));
    }

    function clearWakeRules() {
      el.wakeRulesList.innerHTML = "";
    }

    function collectWakeRules() {
      const items = Array.from(el.wakeRulesList.querySelectorAll(".rule-item"));
      return items.map((item) => {
        const type = normalizeWakeRuleType(item.querySelector("select").value);
        const valueInput = item.querySelector("input");
        const raw = (valueInput.value || "").trim();
        if (type === "keyword") {
          return { type, value: raw.split(",").map((s) => s.trim()).filter(Boolean) };
        }
        if (type === "prefix" || type === "regex") {
          return { type, value: raw };
        }
        return { type, value: "" };
      }).filter((rule) => rule.type);
    }

    function fillEmptyGroupForm() {
      el.groupId.value = "";
      el.enabled.value = "1";
      el.whitelist.value = "";
      el.blacklist.value = "";
      el.wakeType.value = "always";
      el.wakeValue.value = "";
      el.wakeMode.value = "any";
      clearWakeRules();
      renderWakeRules([]);
      updateWakeHint();
    }

    function fillGroupForm(group) {
      el.groupId.value = group.group_id;
      el.enabled.value = group.enabled ? "1" : "0";
      el.whitelist.value = (group.whitelist || []).join("\n");
      el.blacklist.value = (group.blacklist || []).join("\n");
      el.wakeType.value = group.wake_type;
      let wakeValue = group.wake_value;
      if (group.wake_type === "keyword" && Array.isArray(wakeValue)) {
        wakeValue = wakeValue.join(",");
      }
      el.wakeValue.value = wakeValue || "";
      el.wakeMode.value = group.wake_mode === "all" ? "all" : "any";
      renderWakeRules(group.wake_rules || []);
      updateWakeHint();
    }

    function collectGroupPayload() {
      const groupId = (el.groupId.value || "").trim();
      if (!groupId) {
        throw new Error("请先输入或选择群号");
      }
      if (groupId.length > 64) {
        throw new Error("群号过长，请控制在 64 字符以内");
      }

      const wakeType = el.wakeType.value;
      const wakeRaw = (el.wakeValue.value || "").trim();
      const wakeMode = el.wakeMode.value === "all" ? "all" : "any";
      let wakeValue = wakeRaw;
      if (wakeType === "keyword") {
        wakeValue = wakeRaw.split(",").map((s) => s.trim()).filter(Boolean);
      }
      if (wakeType === "mention" || wakeType === "always") {
        wakeValue = "";
      }

      let wakeRules = collectWakeRules();
      if (wakeRules.length === 0) {
        wakeRules = [{ type: wakeType, value: wakeValue }];
      }

      return {
        group_id: groupId,
        enabled: el.enabled.value === "1",
        whitelist: normalizeWhitelist(el.whitelist.value),
        blacklist: normalizeWhitelist(el.blacklist.value),
        wake_type: wakeType,
        wake_value: wakeValue,
        wake_mode: wakeMode,
        wake_rules: wakeRules,
      };
    }

    async function loadSettings() {
      const data = await api("/api/settings");
      const s = data.settings || {};
      el.settingPort.value = String(s.web_port || 8010);
      el.settingToken.value = String(s.web_token || "");
      el.settingAutoStart.value = s.web_auto_start ? "1" : "0";
      refreshKpi();
      setStatus(el.settingsStatus, "全局设置已加载", "ok");
    }

    async function saveSettings() {
      const port = parseInt(el.settingPort.value || "0", 10);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new Error("端口范围必须为 1-65535");
      }

      const tk = (el.settingToken.value || "").trim();
      if (!tk) {
        throw new Error("token 不能为空");
      }

      await api("/api/settings", {
        method: "POST",
        body: JSON.stringify({
          web_port: port,
          web_token: tk,
          web_auto_start: el.settingAutoStart.value === "1",
        }),
      });

      refreshKpi();
      setStatus(el.settingsStatus, "全局设置保存成功（重启管理页后端口/token立即生效）", "warn");
    }

    function renderGroupSelect() {
      el.groupSelect.innerHTML = "";
      if (state.groups.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "暂无配置";
        el.groupSelect.appendChild(opt);
      } else {
        state.groups.forEach((gid) => {
          const opt = document.createElement("option");
          opt.value = gid;
          opt.textContent = gid;
          el.groupSelect.appendChild(opt);
        });
      }
      refreshKpi();
    }

    async function loadGroups(preferredGroupId) {
      const data = await api("/api/groups");
      state.groups = Array.isArray(data.groups) ? data.groups : [];
      renderGroupSelect();

      if (state.groups.length === 0) {
        state.currentGroupId = "";
        fillEmptyGroupForm();
        return;
      }

      const target = preferredGroupId && state.groups.includes(preferredGroupId)
        ? preferredGroupId
        : state.currentGroupId && state.groups.includes(state.currentGroupId)
          ? state.currentGroupId
          : state.groups[0];

      el.groupSelect.value = target;
      await loadGroup(target);
    }

    async function loadGroup(groupId) {
      if (!groupId) {
        fillEmptyGroupForm();
        return;
      }
      const data = await api("/api/group?group_id=" + encodeURIComponent(groupId));
      const group = data.group;
      state.currentGroupId = group.group_id;
      fillGroupForm(group);
      setStatus(el.groupStatus, "已加载群配置: " + group.group_id, "ok");
    }

    async function addGroup() {
      const gid = (el.newGroupId.value || "").trim();
      if (!gid) {
        throw new Error("请输入群号");
      }
      if (gid.length > 64) {
        throw new Error("群号过长，请控制在 64 字符以内");
      }

      el.groupId.value = gid;
      el.enabled.value = "1";
      el.whitelist.value = "";
      el.blacklist.value = "";
      el.wakeType.value = "always";
      el.wakeValue.value = "";
      el.wakeMode.value = "any";
      clearWakeRules();
      renderWakeRules([]);
      updateWakeHint();

      await api("/api/group", {
        method: "POST",
        body: JSON.stringify(collectGroupPayload()),
      });

      await loadGroups(gid);
      el.newGroupId.value = "";
      setStatus(el.groupStatus, "新增成功: " + gid, "ok");
    }

    async function saveGroup() {
      const payload = collectGroupPayload();
      await api("/api/group", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadGroups(payload.group_id);
      setStatus(el.groupStatus, "保存成功: " + payload.group_id, "ok");
    }

    async function deleteGroup() {
      const gid = (el.groupId.value || "").trim();
      if (!gid) {
        throw new Error("请先选择群配置");
      }

      const yes = window.confirm("确认删除群 " + gid + " 的配置吗？删除后将恢复默认行为。");
      if (!yes) {
        return;
      }

      await api("/api/group?group_id=" + encodeURIComponent(gid), { method: "DELETE" });
      state.currentGroupId = "";
      await loadGroups();
      setStatus(el.groupStatus, "删除成功: " + gid, "ok");
    }

    async function withBusy(task, statusTarget) {
      if (state.loading) return;
      setBusy(true);
      try {
        await task();
      } catch (err) {
        const message = err && err.message ? err.message : String(err);
        setStatus(statusTarget, message, "err");
      } finally {
        setBusy(false);
      }
    }

    async function copyAccessUrl() {
      const url = getCurrentAccessUrl();
      try {
        await navigator.clipboard.writeText(url);
        setStatus(el.settingsStatus, "访问地址已复制", "ok");
      } catch (_) {
        setStatus(el.settingsStatus, "复制失败，请手动复制: " + url, "warn");
      }
    }

    function bindEvents() {
      el.wakeType.addEventListener("change", updateWakeHint);
      el.settingPort.addEventListener("input", refreshKpi);
      el.settingAutoStart.addEventListener("change", refreshKpi);
      el.addWakeRuleBtn.addEventListener("click", () => {
        withBusy(() => { addEmptyWakeRule(); }, el.groupStatus);
      });
      el.clearWakeRulesBtn.addEventListener("click", () => {
        withBusy(() => { clearWakeRules(); }, el.groupStatus);
      });

      el.groupSelect.addEventListener("change", () => {
        withBusy(() => loadGroup(el.groupSelect.value), el.groupStatus);
      });

      el.addGroupBtn.addEventListener("click", () => {
        withBusy(addGroup, el.groupStatus);
      });

      el.saveBtn.addEventListener("click", () => {
        withBusy(saveGroup, el.groupStatus);
      });

      el.deleteBtn.addEventListener("click", () => {
        withBusy(deleteGroup, el.groupStatus);
      });

      el.refreshBtn.addEventListener("click", () => {
        withBusy(() => loadGroups(), el.groupStatus);
      });

      el.saveSettingsBtn.addEventListener("click", () => {
        withBusy(saveSettings, el.settingsStatus);
      });

      el.copyUrlBtn.addEventListener("click", () => {
        withBusy(copyAccessUrl, el.settingsStatus);
      });
    }

    async function init() {
      setStatus(el.groupStatus, "加载中...", "warn");
      setStatus(el.settingsStatus, "加载中...", "warn");
      updateWakeHint();
      bindEvents();

      await loadSettings();
      await loadGroups();

      setStatus(el.groupStatus, "就绪", "ok");
      setStatus(el.settingsStatus, "就绪", "ok");
    }

    init().catch((err) => {
      const message = err && err.message ? err.message : String(err);
      setStatus(el.groupStatus, "初始化失败: " + message, "err");
      setStatus(el.settingsStatus, "初始化失败: " + message, "err");
    });
  </script>
</body>
</html>
"""
