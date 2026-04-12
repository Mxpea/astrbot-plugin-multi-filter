import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Tuple
import urllib.parse

from .store import GroupConfigStore
from .models import (
    GroupConfig,
    VALID_RULE_TYPES,
    _normalize_rule_groups,
)
from .admin_page import render_admin_page
from .observability import RequestTrace, log_request_end, log_request_start


MAX_POST_BODY_BYTES = 1_000_000
MAX_WEB_THREADS = 32
SESSION_COOKIE_NAME = "mf_session"
SESSION_TTL_SECONDS = 12 * 60 * 60


class LimitedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, max_threads: int = MAX_WEB_THREADS):
        super().__init__(server_address, RequestHandlerClass)
        self._max_threads_sem = threading.BoundedSemaphore(max_threads)

    def process_request(self, request, client_address):
        self._max_threads_sem.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._max_threads_sem.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._max_threads_sem.release()


def _split_values(raw: str) -> List[str]:
    s = str(raw or "").replace("，", ",").replace("；", ";")
    parts = re.split(r"[,;|\n\r]+", s)
    return [p.strip() for p in parts if p and p.strip()]


def _parse_rule_value_for_type(rule_type: str, value: Any) -> Any:
    if rule_type == "keyword":
        return _split_values(json.dumps(value, ensure_ascii=False)) if isinstance(value, list) else _split_values(str(value or ""))
    if rule_type == "regex" and isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if rule_type == "mention" or rule_type == "always":
        return ""
    return value if not isinstance(value, list) else [str(x).strip() for x in value if str(x).strip()]


def _derive_primary_rule(groups: List[Dict[str, Any]], fallback_type: str, fallback_value: Any) -> Tuple[str, str, str]:
    primary_type = str(fallback_type or "always").strip().lower()
    primary_value: Any = fallback_value
    primary_mode = "any"

    if groups:
        first_group = groups[0] if isinstance(groups[0], dict) else {}
        primary_mode = str(first_group.get("group_mode", "any") or "any").strip().lower()
        if primary_mode not in {"any", "all"}:
            primary_mode = "any"
        raw_rules = first_group.get("rules", []) if isinstance(first_group.get("rules", []), list) else []
        if raw_rules:
            first_rule = raw_rules[0] if isinstance(raw_rules[0], dict) else {}
            primary_type = str(first_rule.get("type", primary_type) or primary_type).strip().lower()
            primary_value = first_rule.get("value", primary_value)

    if primary_type == "keyword":
        if isinstance(primary_value, list):
            keyword_values = [str(x).strip() for x in primary_value if str(x).strip()]
        else:
            try:
                parsed = json.loads(str(primary_value or ""))
                if isinstance(parsed, list):
                    keyword_values = [str(x).strip() for x in parsed if str(x).strip()]
                else:
                    keyword_values = _split_values(str(primary_value or ""))
            except Exception:
                keyword_values = _split_values(str(primary_value or ""))
        primary_value = json.dumps(keyword_values, ensure_ascii=False)
    elif primary_type in {"prefix", "regex"}:
        if isinstance(primary_value, list):
            primary_value = "\n".join([str(x).strip() for x in primary_value if str(x).strip()])
        else:
            primary_value = str(primary_value or "")
    else:
        primary_value = ""

    return primary_type, primary_value, primary_mode


def _parse_wake_rules_text(raw_text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
    rules: List[Dict[str, Any]] = []

    for ln in lines:
        if ":" in ln:
            t, v = ln.split(":", 1)
        else:
            t, v = ln, ""

        t = str(t or "").strip().lower()
        v = str(v or "").strip()
        if not t:
            continue

        # 支持一条规则中配置多个类型: keyword|regex
        type_tokens = [x.strip() for x in re.split(r"[|,;/\n\r]+", t) if x and x.strip()]
        if not type_tokens:
            continue

        normalized_types: List[str] = []
        for tt in type_tokens:
            if tt in VALID_RULE_TYPES:
                normalized_types.append(tt)

        if not normalized_types:
            continue

        merged_type = "|".join(normalized_types)
        rule_value: Any = _split_values(v) if "keyword" in normalized_types else v
        rules.append({"type": merged_type, "value": rule_value, "invert": False})

    if not rules:
        return []
    return [{"group_mode": "any", "rules": rules}]


def _parse_wake_rules_rows(form_data: Dict[str, List[str]], max_rows: int = 4) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []

    for i in range(1, max_rows + 1):
        t = str((form_data.get(f"rule_type_{i}", [""])[0]) or "").strip().lower()
        v = str((form_data.get(f"rule_value_{i}", [""])[0]) or "").strip()
        if not t or t not in VALID_RULE_TYPES:
            continue

        if t == "keyword":
            rules.append({"type": t, "value": _split_values(v), "invert": False})
        else:
            rules.append({"type": t, "value": v, "invert": False})

    if not rules:
        return []
    group_mode = str(form_data.get("wake_mode", ["any"])[0]).strip().lower()
    if group_mode not in {"any", "all"}:
        group_mode = "any"
    return [{"group_mode": group_mode, "rules": rules}]


def _parse_wake_rules_json(form_data: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    raw = str((form_data.get("wake_rules_json", [""])[0]) or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []

    if not isinstance(parsed, list):
        return []

    groups = _normalize_rule_groups(parsed, default_mode=str(form_data.get("wake_mode", ["any"])[0]).strip().lower())
    return groups


def _normalize_string_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return _split_values(text)


def _normalize_wake_rules(raw_rules: Any) -> List[Dict[str, Any]]:
    return _normalize_rule_groups(raw_rules)


def _build_group_config_from_form(form_data: Dict[str, List[str]]) -> GroupConfig | None:
    group_id = str(form_data.get("group_id", [""])[0]).strip()
    if not group_id:
        return None

    enabled = "enabled" in form_data
    whitelist = _normalize_string_list(form_data.get("whitelist", [""])[0])
    blacklist = _normalize_string_list(form_data.get("blacklist", [""])[0])

    wake_type = str(form_data.get("wake_type", ["always"])[0]).strip().lower()
    if wake_type not in VALID_RULE_TYPES:
        wake_type = "always"

    wake_mode = str(form_data.get("wake_mode", ["any"])[0]).strip().lower()
    if wake_mode not in {"any", "all"}:
        wake_mode = "any"

    wv_str = str(form_data.get("wake_value", [""])[0]).strip()
    wake_rules_text = form_data.get("wake_rules_text", [""])[0]

    if str(wake_rules_text or "").strip().lower() in {"always", "always:"}:
        wake_rules_text = ""

    wake_rules = _parse_wake_rules_json(form_data)
    if not wake_rules:
        wake_rules = _parse_wake_rules_rows(form_data)
    if not wake_rules:
        wake_rules = _parse_wake_rules_text(wake_rules_text)
    if not wake_rules:
        fallback_rule_value = _parse_rule_value_for_type(wake_type, wv_str)
        wake_rules = [{"group_mode": wake_mode, "rules": [{"type": wake_type, "value": fallback_rule_value, "invert": False}]}]

    wake_type, wake_value, wake_mode = _derive_primary_rule(wake_rules, wake_type, wv_str)

    return GroupConfig(
        group_id=group_id,
        enabled=enabled,
        whitelist=whitelist,
        blacklist=blacklist,
        wake_type=wake_type,
        wake_value=wake_value,
        wake_mode=wake_mode,
        wake_rules=wake_rules,
    )


def _group_from_payload(payload: Dict[str, Any]) -> GroupConfig | None:
    if not isinstance(payload, dict):
        return None

    group_id = str(payload.get("group_id", "") or "").strip()
    if not group_id:
        return None

    enabled = bool(payload.get("enabled", True))
    whitelist = _normalize_string_list(payload.get("whitelist", []))
    blacklist = _normalize_string_list(payload.get("blacklist", []))

    wake_type = str(payload.get("wake_type", "always") or "always").strip().lower()
    if wake_type not in {"keyword", "prefix", "regex", "mention", "always"}:
        wake_type = "always"

    wake_mode = str(payload.get("wake_mode", "any") or "any").strip().lower()
    if wake_mode not in {"any", "all"}:
        wake_mode = "any"

    wake_value_raw = payload.get("wake_value", "")
    wake_rules = _normalize_wake_rules(payload.get("wake_rules", []))
    if not wake_rules:
        fallback_rule_value = _parse_rule_value_for_type(wake_type, wake_value_raw)
        wake_rules = [{"group_mode": wake_mode, "rules": [{"type": wake_type, "value": fallback_rule_value, "invert": False}]}]

    wake_type, wake_value, wake_mode = _derive_primary_rule(wake_rules, wake_type, wake_value_raw)

    return GroupConfig(
        group_id=group_id,
        enabled=enabled,
        whitelist=whitelist,
        blacklist=blacklist,
        wake_type=wake_type,
        wake_value=wake_value,
        wake_mode=wake_mode,
        wake_rules=wake_rules,
    )


def _build_export_payload(groups: List[Dict[str, Any]], settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "settings": {
            "web_allow_external_access": bool((settings or {}).get("web_allow_external_access", False)),
        },
        "groups": groups,
    }

class WebManager:
    def __init__(self, config: Dict[str, Any], config_store, group_store: GroupConfigStore, logger: Any):
        self.config = config
        self.config_store = config_store
        self.group_store = group_store
        self.logger = logger
        self.server = None
        self.thread = None
        self._lock = threading.RLock()
        self._msg = "" # Error or Success message flash
        self._sessions: Dict[str, float] = {}

    def _is_valid_token(self, token: str) -> bool:
        expected = str(self.config.get("web_token", "")).strip()
        return bool(token and expected and token == expected)

    def _create_session(self) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[sid] = time.time() + SESSION_TTL_SECONDS
        return sid

    def _is_session_valid(self, sid: str) -> bool:
        if not sid:
            return False
        now = time.time()
        with self._lock:
            exp = self._sessions.get(sid)
            if not exp:
                return False
            if exp < now:
                self._sessions.pop(sid, None)
                return False
            # 滑动续期
            self._sessions[sid] = now + SESSION_TTL_SECONDS
            return True

    def _cleanup_sessions(self):
        now = time.time()
        with self._lock:
            for sid, exp in list(self._sessions.items()):
                if exp < now:
                    self._sessions.pop(sid, None)

    def _bind_host(self) -> str:
        return "0.0.0.0" if bool(self.config.get("web_allow_external_access", False)) else "127.0.0.1"

    def is_running(self) -> bool:
        with self._lock:
            return self.server is not None

    def start(self) -> Tuple[bool, str]:
        with self._lock:
            if self.server is not None:
                if self.thread is None or not self.thread.is_alive():
                    # 清理异常残留状态，允许重新启动
                    try:
                        self.server.server_close()
                    except Exception:
                        pass
                    self.server = None
                    self.thread = None
                else:
                    return True, "管理页已在运行"
            port = int(self.config.get("web_port", 8010))
            host = self._bind_host()
            try:
                Handler = self._build_http_handler()
                self.server = LimitedThreadingHTTPServer((host, port), Handler)
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=False)
                self.thread.start()
                if host == "0.0.0.0":
                    msg = f"管理页启动成功。已允许外网访问，监听 0.0.0.0:{port}"
                else:
                    msg = f"管理页启动成功。地址: http://127.0.0.1:{port}/"
                self.logger.info(f"[multi_filter] {msg}")
                return True, msg
            except Exception as ex:
                return False, str(ex)

    def stop(self) -> Tuple[bool, str]:
        with self._lock:
            if self.server is None:
                return True, "管理页已关闭"
            server = self.server
            thread = self.thread

        try:
            server.shutdown()
            server.server_close()
        except Exception as ex:
            return False, str(ex)

        if thread and thread.is_alive():
            thread.join(timeout=3)
            if thread.is_alive():
                self.logger.warning("[multi_filter] 管理页线程在关闭时未能及时退出，可能仍在运行")
                with self._lock:
                    self.server = server
                    self.thread = thread
                return False, "管理页关闭超时，服务器线程仍在运行，请稍后重试"

        with self._lock:
            self.server = None
            self.thread = None
        return True, "管理页已关闭"

    def get_and_clear_msg(self) -> str:
        with self._lock:
            msg = self._msg
            self._msg = ""
            return msg

    def set_msg(self, msg: str):
        with self._lock:
            self._msg = msg

    def _build_http_handler(self) -> type:
        mgr = self
        
        class MultiFilterHandler(BaseHTTPRequestHandler):
            def _parse_cookie(self) -> Dict[str, str]:
                raw = self.headers.get("Cookie", "")
                pairs = [x.strip() for x in raw.split(";") if x.strip()]
                out: Dict[str, str] = {}
                for pair in pairs:
                    if "=" not in pair:
                        continue
                    k, v = pair.split("=", 1)
                    out[k.strip()] = v.strip()
                return out

            def _get_session_id(self) -> str:
                cookies = self._parse_cookie()
                return cookies.get(SESSION_COOKIE_NAME, "")

            def _set_session_cookie(self, sid: str):
                self.send_header(
                    "Set-Cookie",
                    f"{SESSION_COOKIE_NAME}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL_SECONDS}",
                )

            def log_message(self, format, *args):
                pass 
                
            def _is_http_authorized(self, qs: Dict[str, List[str]]) -> bool:
                if mgr._is_session_valid(self._get_session_id()):
                    return True

                qs_token = str(qs.get("token", [""])[0]).strip()
                if mgr._is_valid_token(qs_token):
                    return True

                auth = str(self.headers.get("Authorization", "")).strip()
                if auth.lower().startswith("bearer "):
                    bearer = auth[7:].strip()
                    if mgr._is_valid_token(bearer):
                        return True

                return False

            def _token_from_request(self, qs: Dict[str, List[str]]) -> str:
                qs_token = str(qs.get("token", [""])[0]).strip()
                if qs_token:
                    return qs_token
                auth = str(self.headers.get("Authorization", "")).strip()
                if auth.lower().startswith("bearer "):
                    return auth[7:].strip()
                return ""

            def _qs_without_token(self, qs: Dict[str, List[str]]) -> str:
                clean_pairs: List[Tuple[str, str]] = []
                for k, vals in qs.items():
                    if k == "token":
                        continue
                    for v in vals:
                        clean_pairs.append((k, v))
                return urllib.parse.urlencode(clean_pairs)

            def _redirect(self, location: str = "/"):
                self.send_response(302)
                self.send_header("Location", location)
                self.end_headers()

            def _send_html(self, html: str, set_cookie_sid: str = ""):
                body = html.encode("utf-8")
                self.send_response(200)
                if set_cookie_sid:
                    self._set_session_cookie(set_cookie_sid)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_text(self, status: int, text: str):
                body = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_login_page(self):
                html = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>登录</title></head>
<body style='font-family: sans-serif; padding: 24px;'>
  <h3>管理页登录</h3>
  <p>请输入配置文件中的 web_token：</p>
  <form method='POST' action='/?op=login'>
    <input type='password' name='token' style='width: 320px; max-width: 100%; padding: 8px;' required>
    <button type='submit' style='padding: 8px 12px; margin-left: 8px;'>登录</button>
  </form>
</body></html>"""
                self._send_html(html)

            def _read_request_data(self) -> Tuple[Dict[str, List[str]], Dict[str, bytes], str]:
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                except Exception:
                    return {}, {}, "bad-content-length"

                if content_len < 0:
                    return {}, {}, "bad-content-length"
                if content_len > MAX_POST_BODY_BYTES:
                    return {}, {}, "payload-too-large"

                post_body = self.rfile.read(content_len)
                content_type = str(self.headers.get("Content-Type", "")).lower()

                if content_type.startswith("multipart/form-data"):
                    form_data: Dict[str, List[str]] = {}
                    files: Dict[str, bytes] = {}
                    try:
                        boundary_match = re.search(r"boundary=([^;]+)", self.headers.get("Content-Type", ""), re.I)
                        if not boundary_match:
                            return {}, {}, "bad-multipart"
                        boundary = boundary_match.group(1).strip().strip('"')
                        boundary_marker = ("--" + boundary).encode("utf-8")
                        parts = post_body.split(boundary_marker)
                        for raw_part in parts:
                            part = raw_part.strip(b"\r\n")
                            if not part or part == b"--":
                                continue
                            if part.endswith(b"--"):
                                part = part[:-2]
                            header_blob, sep, part_body = part.partition(b"\r\n\r\n")
                            if not sep:
                                continue
                            header_lines = header_blob.decode("utf-8", errors="ignore").split("\r\n")
                            header_map: Dict[str, str] = {}
                            for line in header_lines:
                                if ":" not in line:
                                    continue
                                key, value = line.split(":", 1)
                                header_map[key.strip().lower()] = value.strip()

                            disposition = header_map.get("content-disposition", "")
                            name_match = re.search(r'name="([^"]+)"', disposition)
                            if not name_match:
                                continue
                            field_name = name_match.group(1)
                            filename_match = re.search(r'filename="([^"]*)"', disposition)
                            content = part_body.rstrip(b"\r\n")
                            if filename_match and filename_match.group(1):
                                files[field_name] = content
                            else:
                                form_data.setdefault(field_name, []).append(content.decode("utf-8", errors="ignore"))
                        return form_data, files, ""
                    except Exception:
                        return {}, {}, "bad-multipart"

                try:
                    parsed = urllib.parse.parse_qs(post_body.decode("utf-8"))
                except Exception:
                    return {}, {}, "bad-encoding"
                return parsed, {}, ""

            def do_GET(self):
                trace = RequestTrace.create("GET", self.path)
                log_request_start(mgr.logger, trace)
                status = 500
                ok = False
                parsed = urllib.parse.urlparse(self.path)
                
                if parsed.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    status = 204
                    ok = True
                    log_request_end(mgr.logger, trace, status, ok)
                    return
                elif parsed.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    status = 200
                    ok = True
                    log_request_end(mgr.logger, trace, status, ok)
                    return

                qs = urllib.parse.parse_qs(parsed.query)
                op = qs.get("op", [""])[0]

                if op == "export":
                    if not self._is_http_authorized(qs):
                        self._send_text(401, "Unauthorized")
                        log_request_end(mgr.logger, trace, 401, False)
                        return

                    groups: List[Dict[str, Any]] = []
                    for gid in mgr.group_store.list_groups():
                        cfg = mgr.group_store.get(gid)
                        if cfg is not None:
                            groups.append(cfg.to_api_dict())

                    payload = _build_export_payload(groups, mgr.config)
                    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                    filename = f"astrbot_plugin_multi_filter_groups_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    log_request_end(mgr.logger, trace, 200, True)
                    return
                if not self._is_http_authorized(qs):
                    self._send_login_page()
                    status = 200
                    ok = True
                    log_request_end(mgr.logger, trace, status, ok)
                    return

                sid = ""
                req_token = self._token_from_request(qs)
                if req_token and not mgr._is_session_valid(self._get_session_id()):
                    sid = mgr._create_session()
                    self.send_response(302)
                    self._set_session_cookie(sid)
                    q = self._qs_without_token(qs)
                    location = f"/?{q}" if q else "/"
                    self.send_header("Location", location)
                    self.end_headers()
                    status = 302
                    ok = True
                    log_request_end(mgr.logger, trace, status, ok)
                    return

                groups: List[Dict[str, Any]] = []
                for gid in mgr.group_store.list_groups():
                    cfg = mgr.group_store.get(gid)
                    if cfg is not None:
                        groups.append(cfg.to_api_dict())
                msg = mgr.get_and_clear_msg()
                html_str = render_admin_page(groups, mgr.config, msg)
                self._send_html(html_str, set_cookie_sid=sid)
                status = 200
                ok = True
                mgr._cleanup_sessions()
                log_request_end(mgr.logger, trace, status, ok)

            def do_POST(self):
                trace = RequestTrace.create("POST", self.path)
                parsed = urllib.parse.urlparse(self.path)
                log_request_start(mgr.logger, trace, {"path": parsed.path})
                status = 500
                ok = False
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                op = qs.get("op", [""])[0]
                form_data, uploaded_files, read_err = self._read_request_data()
                if read_err == "payload-too-large":
                    self._send_text(413, "Payload Too Large")
                    log_request_end(mgr.logger, trace, 413, False)
                    return
                if read_err:
                    self._send_text(400, "Bad Request")
                    log_request_end(mgr.logger, trace, 400, False)
                    return

                if op == "login":
                    submitted = str(form_data.get("token", [""])[0]).strip()
                    if not mgr._is_valid_token(submitted):
                        self._send_text(401, "Unauthorized")
                        log_request_end(mgr.logger, trace, 401, False)
                        return
                    sid = mgr._create_session()
                    self.send_response(302)
                    self._set_session_cookie(sid)
                    self.send_header("Location", "/")
                    self.end_headers()
                    log_request_end(mgr.logger, trace, 302, True)
                    return
                
                if not self._is_http_authorized(qs):
                    self._send_text(401, "Unauthorized")
                    log_request_end(mgr.logger, trace, 401, False)
                    return

                if op == "import":
                    replace_existing = "replace_existing" in form_data
                    raw_bytes = uploaded_files.get("import_file", b"")
                    if not raw_bytes:
                        raw_text = str(form_data.get("import_json", [""])[0]).strip()
                        raw_bytes = raw_text.encode("utf-8")

                    if not raw_bytes:
                        self._send_text(400, "No import file provided")
                        log_request_end(mgr.logger, trace, 400, False)
                        return

                    try:
                        imported = json.loads(raw_bytes.decode("utf-8"))
                    except Exception as ex:
                        self._send_text(400, f"Invalid JSON: {ex}")
                        log_request_end(mgr.logger, trace, 400, False)
                        return

                    if isinstance(imported, dict):
                        group_items = imported.get("groups", [])
                    else:
                        group_items = imported

                    if not isinstance(group_items, list):
                        self._send_text(400, "JSON must be a list or contain a groups list")
                        log_request_end(mgr.logger, trace, 400, False)
                        return

                    group_configs: List[GroupConfig] = []
                    skipped = 0
                    for item in group_items:
                        cfg = _group_from_payload(item)
                        if cfg is None:
                            skipped += 1
                            continue
                        group_configs.append(cfg)

                    if replace_existing and not group_configs:
                        self._send_text(400, "No valid group configs found in import file")
                        log_request_end(mgr.logger, trace, 400, False)
                        return

                    if replace_existing:
                        mgr.group_store.clear_all()

                    for cfg in group_configs:
                        mgr.group_store.upsert(cfg)

                    mgr.set_msg(
                        f"导入完成: 成功 {len(group_configs)} 条，跳过 {skipped} 条。"
                        + (" 已覆盖原有配置。" if replace_existing else " 已合并到现有配置。")
                    )
                    self._redirect("/")
                    status = 302
                    ok = True
                    mgr._cleanup_sessions()
                    log_request_end(mgr.logger, trace, status, ok)
                    return
                
                try:
                    if op == "add":
                        group_id = form_data.get("group_id", [""])[0].strip()
                        if group_id == "__default__":
                            mgr.set_msg("__default__ 为系统保留标识，请勿手动新增。")
                            self._redirect("/")
                            log_request_end(mgr.logger, trace, 302, False)
                            return
                        if group_id:
                            if mgr.group_store.get(group_id):
                                mgr.set_msg(f"群 {group_id} 已存在！")
                            else:
                                new_cfg = GroupConfig(
                                    group_id=group_id,
                                    enabled=True,
                                    whitelist=[],
                                    blacklist=[],
                                    wake_type="always",
                                    wake_value="",
                                    wake_mode="any",
                                    wake_rules=[]
                                )
                                mgr.group_store.upsert(new_cfg)
                                mgr.set_msg(f"成功增加群 {group_id}，请继续配置。")
                    elif op == "delete":
                        group_id = form_data.get("group_id", [""])[0].strip()
                        if not group_id:
                            mgr.set_msg("删除失败: group_id 不能为空。")
                            self._redirect("/")
                            log_request_end(mgr.logger, trace, 302, False)
                            return
                        if group_id == "__default__":
                            mgr.set_msg("默认群配置不可删除，可改为停用。")
                            self._redirect("/")
                            log_request_end(mgr.logger, trace, 302, False)
                            return
                        mgr.group_store.delete(group_id)
                        mgr.set_msg(f"已删除群 {group_id} 的配置。")
                    elif op == "save":
                        new_cfg = _build_group_config_from_form(form_data)
                        if new_cfg is None:
                            mgr.set_msg("保存失败: group_id 不能为空。")
                            self._redirect("/")
                            log_request_end(mgr.logger, trace, 302, False)
                            return
                        mgr.group_store.upsert(new_cfg)
                        mgr.set_msg(f"群 {new_cfg.group_id} 配置保存成功。")
                    else:
                        mgr.set_msg("未知操作。")
                        
                except Exception as e:
                    mgr.logger.error(f"[multi_filter] POST error: {str(e)}")
                    mgr.set_msg(f"操作失败: {str(e)}")
                    
                self._redirect("/")
                status = 302
                ok = True
                mgr._cleanup_sessions()
                log_request_end(mgr.logger, trace, status, ok)
                
        return MultiFilterHandler
