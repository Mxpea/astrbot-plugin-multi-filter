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
    .hint { color: var(--muted); font-size: 12px; margin-top: 5px; }
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
    input:focus, select:focus, textarea:focus {
      border-color: var(--main);
    }
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
      transition: background .15s ease;
    }
    button:hover { background: var(--main-dark); }
    button.secondary { background: #6e7f92; }
    button.secondary:hover { background: #596a7d; }
    button.danger { background: var(--danger); }
    button.danger:hover { background: #ad2323; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .split {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 14px;
    }
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
    @media (max-width: 900px) {
      .split { grid-template-columns: 1fr; }
      .col, .col-sm { min-width: 0; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <h1 class=\"title\">Multi Filter 管理页面</h1>
      <p class=\"subtitle\">此页面使用 token 鉴权，建议仅在本机访问并定期轮换 token。</p>
      <div style=\"margin-top:10px;\">
        <span class=\"kpi\" id=\"kpiGroups\">已配置群: 0</span>
        <span class=\"kpi\" id=\"kpiPort\">端口: -</span>
        <span class=\"kpi\" id=\"kpiAutoStart\">自启: -</span>
      </div>
    </div>

    <div class=\"split\">
      <div class=\"card\">
        <h3 style=\"margin:0 0 12px;\">群规则管理</h3>
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
      wakeType: $("wakeType"),
      wakeValue: $("wakeValue"),
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
      const hint = getWakeHint(wakeType);
      el.wakeHint.textContent = hint;

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

    function fillEmptyGroupForm() {
      el.groupId.value = "";
      el.enabled.value = "1";
      el.whitelist.value = "";
      el.wakeType.value = "always";
      el.wakeValue.value = "";
      updateWakeHint();
    }

    function fillGroupForm(group) {
      el.groupId.value = group.group_id;
      el.enabled.value = group.enabled ? "1" : "0";
      el.whitelist.value = (group.whitelist || []).join("\n");
      el.wakeType.value = group.wake_type;
      let wakeValue = group.wake_value;
      if (group.wake_type === "keyword" && Array.isArray(wakeValue)) {
        wakeValue = wakeValue.join(",");
      }
      el.wakeValue.value = wakeValue || "";
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
      let wakeValue = wakeRaw;
      if (wakeType === "keyword") {
        wakeValue = wakeRaw.split(",").map((s) => s.trim()).filter(Boolean);
      }
      if (wakeType === "mention" || wakeType === "always") {
        wakeValue = "";
      }

      return {
        group_id: groupId,
        enabled: el.enabled.value === "1",
        whitelist: normalizeWhitelist(el.whitelist.value),
        wake_type: wakeType,
        wake_value: wakeValue,
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
      el.wakeType.value = "always";
      el.wakeValue.value = "";
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
