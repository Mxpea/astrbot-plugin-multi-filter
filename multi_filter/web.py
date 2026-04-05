import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Tuple
import urllib.parse

from .store import GroupConfigStore
from .models import GroupConfig
from .admin_page import render_admin_page


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

    def is_running(self) -> bool:
        with self._lock:
            return self.server is not None

    def start(self) -> Tuple[bool, str]:
        with self._lock:
            if self.server is not None:
                return True, "管理页已在运行"
            port = int(self.config.get("web_port", 8010))
            token = str(self.config.get("web_token", "change-me"))
            try:
                Handler = self._build_http_handler()
                self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
                self.server.token = token 
                self.server.web_manager = self
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
                msg = f"管理页启动成功。地址: http://127.0.0.1:{port}/?token={token}"
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
            def log_message(self, format, *args):
                pass 
                
            def _is_http_authorized(self, qs_token: str) -> bool:
                token = str(mgr.config.get("web_token", "change-me"))
                return qs_token == token

            def _redirect(self, token: str):
                self.send_response(302)
                self.send_header("Location", f"/?token={token}")
                self.end_headers()

            def _send_html(self, html: str):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                
                if parsed.path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                elif parsed.path == "/health":
                    self.send_response(200)
                    self.end_headers()
                    return

                qs = urllib.parse.parse_qs(parsed.query)
                token = (qs.get("token", [""])[0])
                if not self._is_http_authorized(token):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"Unauthorized")
                    return

                groups = [mgr.group_store.get(gid).to_api_dict() for gid in mgr.group_store.list_groups() if mgr.group_store.get(gid)]
                msg = mgr.get_and_clear_msg()
                html_str = render_admin_page(groups, token, msg)
                self._send_html(html_str)

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                token = qs.get("token", [""])[0]
                op = qs.get("op", [""])[0]
                
                if not self._is_http_authorized(token):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"Unauthorized")
                    return
                    
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8")
                form_data = urllib.parse.parse_qs(post_body)
                
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
                        mgr.group_store.delete(group_id)
                        mgr.set_msg(f"已删除群 {group_id} 的配置。")
                    elif op == "save":
                        group_id = form_data.get("group_id", [""])[0].strip()
                        enabled = "enabled" in form_data
                        
                        wl_str = form_data.get("whitelist", [""])[0].strip()
                        bl_str = form_data.get("blacklist", [""])[0].strip()
                        whitelist = [x.strip() for x in wl_str.replace("，", ",").split(",") if x.strip()]
                        blacklist = [x.strip() for x in bl_str.replace("，", ",").split(",") if x.strip()]
                        
                        wake_type = form_data.get("wake_type", ["always"])[0].strip()
                        wake_mode = form_data.get("wake_mode", ["any"])[0].strip()
                        
                        wv_str = form_data.get("wake_value", [""])[0].strip()
                        wake_rules_text = form_data.get("wake_rules_text", [""])[0]
                        
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
                        
                except Exception as e:
                    mgr.logger.error(f"[multi_filter] POST error: {str(e)}")
                    mgr.set_msg(f"操作失败: {str(e)}")
                    
                self._redirect(token)
                
        return MultiFilterHandler
