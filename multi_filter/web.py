import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Tuple
import urllib.parse

from .store import GroupConfigStore
from .models import GroupConfig
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


def _parse_wake_rules_text(raw_text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
    rules: List[Dict[str, Any]] = []
    valid_types = {"keyword", "prefix", "regex", "mention", "always"}

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
            if tt in valid_types:
                normalized_types.append(tt)

        if not normalized_types:
            continue

        merged_type = "|".join(normalized_types)

        if "keyword" in normalized_types:
            rules.append({"type": merged_type, "value": _split_values(v)})
        else:
            rules.append({"type": merged_type, "value": v})

    return rules


def _parse_wake_rules_rows(form_data: Dict[str, List[str]], max_rows: int = 4) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    valid_types = {"keyword", "prefix", "regex", "mention", "always"}

    for i in range(1, max_rows + 1):
        t = str((form_data.get(f"rule_type_{i}", [""])[0]) or "").strip().lower()
        v = str((form_data.get(f"rule_value_{i}", [""])[0]) or "").strip()
        if not t or t not in valid_types:
            continue

        if t == "keyword":
            rules.append({"type": t, "value": _split_values(v)})
        else:
            rules.append({"type": t, "value": v})

    return rules

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

    def is_running(self) -> bool:
        with self._lock:
            return self.server is not None

    def start(self) -> Tuple[bool, str]:
        with self._lock:
            if self.server is not None:
                return True, "管理页已在运行"
            port = int(self.config.get("web_port", 8010))
            try:
                Handler = self._build_http_handler()
                self.server = LimitedThreadingHTTPServer(("127.0.0.1", port), Handler)
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
                msg = f"管理页启动成功。地址: http://127.0.0.1:{port}/"
                self.logger.info(f"[multi_filter] {msg}")
                return True, msg
            except Exception as ex:
                return False, str(ex)

    def stop(self) -> Tuple[bool, str]:
        with self._lock:
            if self.server is None:
                return True, "管理页已关闭"
            try:
                self.server.shutdown()
                self.server.server_close()
                self.server = None
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=2)
                self.thread = None
                return True, "管理页已关闭"
            except Exception as ex:
                self.server = None
                self.thread = None
                return False, str(ex)

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

            def _read_form_data(self) -> Tuple[Dict[str, List[str]], str]:
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                except Exception:
                    return {}, "bad-content-length"

                if content_len < 0:
                    return {}, "bad-content-length"
                if content_len > MAX_POST_BODY_BYTES:
                    return {}, "payload-too-large"

                post_body = self.rfile.read(content_len)
                try:
                    parsed = urllib.parse.parse_qs(post_body.decode("utf-8"))
                except Exception:
                    return {}, "bad-encoding"
                return parsed, ""

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
                html_str = render_admin_page(groups, msg)
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
                form_data, read_err = self._read_form_data()
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
                
                try:
                    if op == "add":
                        group_id = form_data.get("group_id", [""])[0].strip()
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
                        mgr.group_store.delete(group_id)
                        mgr.set_msg(f"已删除群 {group_id} 的配置。")
                    elif op == "save":
                        group_id = form_data.get("group_id", [""])[0].strip()
                        enabled = "enabled" in form_data
                        
                        wl_str = form_data.get("whitelist", [""])[0].strip()
                        bl_str = form_data.get("blacklist", [""])[0].strip()
                        whitelist = _split_values(wl_str)
                        blacklist = _split_values(bl_str)
                        
                        wake_type = form_data.get("wake_type", ["always"])[0].strip().lower()
                        wake_mode = form_data.get("wake_mode", ["any"])[0].strip().lower()
                        if wake_mode not in {"any", "all"}:
                            wake_mode = "any"
                        
                        wv_str = form_data.get("wake_value", [""])[0].strip()
                        wake_rules_text = form_data.get("wake_rules_text", [""])[0]

                        txt_norm = str(wake_rules_text or "").strip().lower()
                        if txt_norm in {"always", "always:"}:
                            wake_rules_text = ""
                        
                        wake_rules = _parse_wake_rules_rows(form_data)
                        if not wake_rules:
                            wake_rules = _parse_wake_rules_text(wake_rules_text)
                        if not wake_rules:
                            # 无高级规则时，回退为单规则并同步到 wake_rules
                            if wake_type == "keyword":
                                wv_list = _split_values(wv_str)
                                wake_rules = [{"type": "keyword", "value": wv_list}]
                            else:
                                wake_rules = [{"type": wake_type, "value": wv_str}]
                        
                        if wake_type == "keyword":
                            wv_list = _split_values(wv_str)
                            wv_json = json.dumps(wv_list, ensure_ascii=False)
                        else:
                            wv_json = wv_str
                            
                        new_cfg = GroupConfig(
                            group_id=group_id,
                            enabled=enabled,
                            whitelist=whitelist,
                            blacklist=blacklist,
                            wake_type=wake_type,
                            wake_value=wv_json,
                            wake_mode=wake_mode,
                            wake_rules=wake_rules
                        )
                        mgr.group_store.upsert(new_cfg)
                        mgr.set_msg(f"群 {group_id} 配置保存成功。")
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
