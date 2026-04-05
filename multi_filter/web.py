import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .admin_page import ADMIN_HTML
from .models import GroupConfig
from .observability import RequestTrace, log_request_end, log_request_start
from .store import GroupConfigStore


VALID_WAKE_TYPES = {"always", "keyword", "prefix", "mention", "regex"}
VALID_WAKE_MODES = {"any", "all"}


class WebManager:
    def __init__(self, config: Dict[str, Any], config_store: Any, group_store: GroupConfigStore, logger: Any):
        self.config = config
        self.config_store = config_store
        self.group_store = group_store
        self.logger = logger

        self._web_server: Optional[ThreadingHTTPServer] = None
        self._web_thread: Optional[threading.Thread] = None
        self._web_lock = threading.RLock()

    def is_running(self) -> bool:
        return (
            self._web_server is not None
            and self._web_thread is not None
            and self._web_thread.is_alive()
        )

    def start(self) -> Tuple[bool, str]:
        with self._web_lock:
            if self.is_running():
                return True, "管理页已在运行"

            port = int(self.config.get("web_port", 8010))
            token = str(self.config.get("web_token", "change-me"))

            try:
                handler_cls = self._build_http_handler()
                server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
                server.daemon_threads = True

                self._web_server = server
                self._web_thread = threading.Thread(
                    target=server.serve_forever,
                    name="multi-filter-web",
                    daemon=True,
                )
                self._web_thread.start()
                self.logger.info("[multi_filter] 管理页启动: http://127.0.0.1:%s/?token=%s", port, token)
                return True, f"管理页已启动: http://127.0.0.1:{port}/?token={token}"
            except Exception as ex:
                self.logger.error("[multi_filter] 启动 Web 服务失败: %s", ex)
                self._web_server = None
                self._web_thread = None
                return False, str(ex)

    def stop(self) -> Tuple[bool, str]:
        with self._web_lock:
            if self._web_server is not None:
                try:
                    self._web_server.shutdown()
                    self._web_server.server_close()
                except Exception as ex:
                    self.logger.error("[multi_filter] 关闭 Web 服务失败: %s", ex)
                    return False, str(ex)
            self._web_server = None
            self._web_thread = None
            return True, "管理页已关闭"

    def _build_http_handler(self):
        manager = self

        class MultiFilterHandler(BaseHTTPRequestHandler):
            server_version = "MultiFilterHTTP/1.0"

            def do_GET(self):
                manager._handle_http_request(self, "GET")

            def do_POST(self):
                manager._handle_http_request(self, "POST")

            def do_DELETE(self):
                manager._handle_http_request(self, "DELETE")

            def log_message(self, fmt: str, *args: Any):
                manager.logger.debug("[multi_filter][web] " + fmt, *args)

        return MultiFilterHandler

    def _handle_http_request(self, handler: BaseHTTPRequestHandler, method: str):
        parsed = urlparse(handler.path)
        path = parsed.path
        q = parse_qs(parsed.query)
        trace = RequestTrace.create(method=method, path=path)
        self._log_http_request_start(trace, q)

        if not self._is_http_authorized(handler, q):
            self._send_json(handler, 401, {"ok": False, "error": "unauthorized"}, trace)
            return

        try:
            if method == "GET" and path == "/health":
                self._send_json(
                    handler,
                    200,
                    {
                        "ok": True,
                        "status": "running",
                        "web_port": int(self.config.get("web_port", 8010)),
                    },
                    trace,
                )
                return

            if method == "GET" and path == "/favicon.ico":
                handler.send_response(204)
                handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                handler.end_headers()
                log_request_end(self.logger, trace, status=204, ok=True)
                return

            if method == "GET" and path == "/":
                op = (q.get("_op") or [""])[0].strip().lower()
                if op == "add_group":
                    group_id = (q.get("group_id") or [""])[0].strip()
                    if not group_id:
                        self._send_html(handler, "<h3>新增失败: 缺少 group_id</h3>", trace)
                        return
                    if len(group_id) > 64:
                        self._send_html(handler, "<h3>新增失败: 群号过长</h3>", trace)
                        return

                    cfg = GroupConfig(
                        group_id=group_id,
                        enabled=True,
                        whitelist=[],
                        blacklist=[],
                        wake_type="always",
                        wake_value="",
                        wake_mode="any",
                        wake_rules=[{"type": "always", "value": ""}],
                    )
                    self.group_store.upsert(cfg)
                    self.logger.info("[multi_filter][web][%s] 表单新增群配置: group_id=%s", trace.trace_id, group_id)
                    self._send_html(
                        handler,
                        (
                            "<h3>新增成功: "
                            + group_id
                            + "</h3><p><a href=\"javascript:history.back()\">返回上一页</a></p>"
                        ),
                        trace,
                    )
                    return

                self._send_html(handler, ADMIN_HTML, trace)
                return

            if method == "GET" and path == "/api/groups":
                groups = self.group_store.list_groups()
                self._send_json(handler, 200, {"ok": True, "groups": groups}, trace)
                return

            if method == "GET" and path == "/api/group":
                group_id = (q.get("group_id") or [""])[0].strip()
                if not group_id:
                    self._send_json(handler, 400, {"ok": False, "error": "missing group_id"}, trace)
                    return
                cfg = self.group_store.get(group_id)
                if cfg is None:
                    self._send_json(handler, 404, {"ok": False, "error": "group not found"}, trace)
                    return
                self._send_json(handler, 200, {"ok": True, "group": cfg.to_api_dict()}, trace)
                return

            if method == "POST" and path == "/api/group":
                payload = self._read_json_body(handler)
                if payload is None:
                    self._send_json(handler, 400, {"ok": False, "error": "invalid json body"}, trace)
                    return

                valid, result = self._parse_api_group_payload(payload)
                if not valid:
                    self._send_json(handler, 400, {"ok": False, "error": result}, trace)
                    return

                cfg = result
                self.group_store.upsert(cfg)
                self.logger.info("[multi_filter][web][%s] 更新群配置: group_id=%s", trace.trace_id, cfg.group_id)
                self._send_json(handler, 200, {"ok": True, "group": cfg.to_api_dict()}, trace)
                return

            if method == "DELETE" and path == "/api/group":
                group_id = (q.get("group_id") or [""])[0].strip()
                if not group_id:
                    self._send_json(handler, 400, {"ok": False, "error": "missing group_id"}, trace)
                    return
                self.group_store.delete(group_id)
                self.logger.info("[multi_filter][web][%s] 删除群配置: group_id=%s", trace.trace_id, group_id)
                self._send_json(handler, 200, {"ok": True}, trace)
                return

            if method == "GET" and path == "/api/settings":
                self._send_json(
                    handler,
                    200,
                    {
                        "ok": True,
                        "settings": {
                            "web_port": int(self.config.get("web_port", 8010)),
                            "web_token": str(self.config.get("web_token", "")),
                            "web_auto_start": bool(self.config.get("web_auto_start", False)),
                            "default_action": str(self.config.get("default_action", "allow")),
                        },
                    },
                    trace,
                )
                return

            if method == "POST" and path == "/api/settings":
                payload = self._read_json_body(handler)
                if payload is None:
                    self._send_json(handler, 400, {"ok": False, "error": "invalid json body"}, trace)
                    return

                if "web_port" in payload:
                    try:
                        port = int(payload.get("web_port", 0))
                    except Exception:
                        self._send_json(handler, 400, {"ok": False, "error": "invalid web_port"}, trace)
                        return
                    if not 1 <= port <= 65535:
                        self._send_json(handler, 400, {"ok": False, "error": "invalid web_port"}, trace)
                        return
                    self.config["web_port"] = port

                if "web_token" in payload:
                    token = str(payload.get("web_token") or "").strip()
                    if not token:
                        self._send_json(handler, 400, {"ok": False, "error": "web_token cannot be empty"}, trace)
                        return
                    self.config["web_token"] = token

                if "web_auto_start" in payload:
                    self.config["web_auto_start"] = bool(payload.get("web_auto_start"))

                if not self.config_store.save(self.config):
                    self._send_json(handler, 500, {"ok": False, "error": "save config failed"}, trace)
                    return

                self.logger.info(
                    "[multi_filter][web][%s] 更新全局设置: web_port=%s web_auto_start=%s",
                    trace.trace_id,
                    self.config.get("web_port"),
                    self.config.get("web_auto_start"),
                )

                self._send_json(
                    handler,
                    200,
                    {
                        "ok": True,
                        "settings": {
                            "web_port": int(self.config.get("web_port", 8010)),
                            "web_token": str(self.config.get("web_token", "")),
                            "web_auto_start": bool(self.config.get("web_auto_start", False)),
                            "default_action": str(self.config.get("default_action", "allow")),
                        },
                    },
                    trace,
                )
                return

            self._send_json(handler, 404, {"ok": False, "error": "not found"}, trace)
        except Exception as ex:
            self.logger.error("[multi_filter][web][%s] Web 请求处理失败: %s", trace.trace_id, ex)
            self._send_json(handler, 500, {"ok": False, "error": "internal error"}, trace)

    def _log_http_request_start(self, trace: RequestTrace, query: Dict[str, List[str]]):
        summarized = {
            "query_keys": sorted(list(query.keys())),
        }
        log_request_start(self.logger, trace, summarized)

    def _is_http_authorized(
        self,
        handler: BaseHTTPRequestHandler,
        query: Dict[str, List[str]],
    ) -> bool:
        token = str(self.config.get("web_token", "change-me"))
        query_token = (query.get("token") or [""])[0]
        if query_token == token:
            return True

        header_token = handler.headers.get("X-Token", "")
        if header_token == token:
            return True

        auth = handler.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == token:
            return True

        # 兼容无脚本表单提交: 从 Referer 中回收 token。
        referer = handler.headers.get("Referer", "")
        if referer:
            try:
                rq = parse_qs(urlparse(referer).query)
                ref_token = (rq.get("token") or [""])[0]
                if ref_token == token:
                    return True
            except Exception:
                pass

        return False

    def _read_json_body(self, handler: BaseHTTPRequestHandler) -> Optional[Dict[str, Any]]:
        try:
            length = int(handler.headers.get("Content-Length", "0"))
        except Exception:
            return None

        raw = handler.rfile.read(length) if length > 0 else b""
        if not raw:
            return None

        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _parse_api_group_payload(self, payload: Dict[str, Any]) -> Tuple[bool, Any]:
        group_id = str(payload.get("group_id", "")).strip()
        if not group_id:
            return False, "group_id is required"

        enabled = bool(payload.get("enabled", True))

        wl_raw = payload.get("whitelist", [])
        if not isinstance(wl_raw, list):
            return False, "whitelist must be array"
        whitelist = [str(x).strip() for x in wl_raw if str(x).strip()]

        bl_raw = payload.get("blacklist", [])
        if not isinstance(bl_raw, list):
            return False, "blacklist must be array"
        blacklist = [str(x).strip() for x in bl_raw if str(x).strip()]

        wake_type = str(payload.get("wake_type", "always")).strip().lower()
        if wake_type not in VALID_WAKE_TYPES:
            return False, f"wake_type must be one of: {sorted(VALID_WAKE_TYPES)}"

        wake_mode = str(payload.get("wake_mode", "any")).strip().lower()
        if wake_mode not in VALID_WAKE_MODES:
            return False, f"wake_mode must be one of: {sorted(VALID_WAKE_MODES)}"

        wake_value_obj = payload.get("wake_value", "")
        wake_value_str = ""

        if wake_type == "keyword":
            if isinstance(wake_value_obj, list):
                keywords = [str(x).strip() for x in wake_value_obj if str(x).strip()]
            elif isinstance(wake_value_obj, str):
                keywords = [x.strip() for x in wake_value_obj.split(",") if x.strip()]
            else:
                return False, "wake_value(keyword) must be array or comma string"
            wake_value_str = json.dumps(keywords, ensure_ascii=False)

        elif wake_type == "prefix":
            wake_value_str = str(wake_value_obj or "")

        elif wake_type == "regex":
            wake_value_str = str(wake_value_obj or "")
            if not wake_value_str:
                return False, "wake_value(regex) cannot be empty"
            try:
                re.compile(wake_value_str)
            except re.error as ex:
                return False, f"invalid regex: {ex}"

        elif wake_type in {"mention", "always"}:
            wake_value_str = ""

        # 多唤醒条件，结构: [{"type":"keyword","value":["a","b"]}, ...]
        wake_rules_obj = payload.get("wake_rules", [])
        if wake_rules_obj is None:
            wake_rules_obj = []
        if not isinstance(wake_rules_obj, list):
            return False, "wake_rules must be array"

        normalized_rules: List[Dict[str, Any]] = []
        for item in wake_rules_obj:
            if not isinstance(item, dict):
                return False, "wake_rules items must be object"
            rule_type = str(item.get("type", "")).strip().lower()
            if rule_type not in VALID_WAKE_TYPES:
                return False, f"wake_rules.type must be one of: {sorted(VALID_WAKE_TYPES)}"

            rule_value = item.get("value", "")
            if rule_type == "keyword":
                if isinstance(rule_value, str):
                    rule_value = [x.strip() for x in rule_value.split(",") if x.strip()]
                if not isinstance(rule_value, list):
                    return False, "wake_rules keyword value must be array or comma string"
                rule_value = [str(x).strip() for x in rule_value if str(x).strip()]
            elif rule_type in {"prefix", "regex"}:
                rule_value = str(rule_value or "")
                if rule_type == "regex" and rule_value:
                    try:
                        re.compile(rule_value)
                    except re.error as ex:
                        return False, f"invalid wake_rules regex: {ex}"
            else:
                rule_value = ""

            normalized_rules.append({"type": rule_type, "value": rule_value})

        # 兼容旧前端: 未传 wake_rules 时，用单规则自动构造。
        if not normalized_rules:
            legacy_value_for_rule: Any = wake_value_obj
            if wake_type == "keyword":
                if isinstance(wake_value_obj, list):
                    legacy_value_for_rule = [str(x).strip() for x in wake_value_obj if str(x).strip()]
                elif isinstance(wake_value_obj, str):
                    legacy_value_for_rule = [x.strip() for x in wake_value_obj.split(",") if x.strip()]
                else:
                    legacy_value_for_rule = []
            elif wake_type in {"prefix", "regex"}:
                legacy_value_for_rule = str(wake_value_obj or "")
            else:
                legacy_value_for_rule = ""

            normalized_rules = [{"type": wake_type, "value": legacy_value_for_rule}]

        cfg = GroupConfig(
            group_id=group_id,
            enabled=enabled,
            whitelist=whitelist,
            blacklist=blacklist,
            wake_type=wake_type,
            wake_value=wake_value_str,
            wake_mode=wake_mode,
            wake_rules=normalized_rules,
        )
        return True, cfg

    def _send_json(
        self,
        handler: BaseHTTPRequestHandler,
        status: int,
        obj: Dict[str, Any],
        trace: Optional[RequestTrace] = None,
    ):
        if trace is not None and isinstance(obj, dict) and "trace_id" not in obj:
            obj = dict(obj)
            obj["trace_id"] = trace.trace_id

        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        if trace is not None:
            handler.send_header("X-Trace-Id", trace.trace_id)
        handler.end_headers()
        handler.wfile.write(body)
        if trace is not None:
            log_request_end(self.logger, trace, status=status, ok=200 <= status < 300)

    def _send_html(self, handler: BaseHTTPRequestHandler, html: str, trace: Optional[RequestTrace] = None):
        body = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        if trace is not None:
            handler.send_header("X-Trace-Id", trace.trace_id)
        handler.end_headers()
        handler.wfile.write(body)
        if trace is not None:
            log_request_end(self.logger, trace, status=200, ok=True)
