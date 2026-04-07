from pathlib import Path
import secrets
import socket
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star

from .config_store import ConfigStore
from .event_logic import (
    extract_port_from_text,
    get_group_id,
    get_text,
    get_user_id,
    interrupt_result,
    is_group_message,
    is_management_command,
    is_self_message,
    should_allow_message,
)
from .store import GroupConfigStore
from .web import WebManager


class MultiFilterPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self._plugin_dir = Path(__file__).resolve().parent.parent

        self.config_store = ConfigStore(self._plugin_dir, logger)
        self.config = self.config_store.load_or_init()

        external_config = dict(config or {})
        if external_config:
            merged = dict(self.config)
            for key in ("web_port", "web_token", "web_allow_external_access", "web_auto_start", "db_path", "default_action"):
                if key in external_config:
                    merged[key] = external_config[key]

            try:
                merged["web_port"] = int(merged.get("web_port", 8010))
            except Exception:
                merged["web_port"] = 8010
            token = str(merged.get("web_token", "")).strip()
            if not token or token == "change-me":
                token = secrets.token_urlsafe(32)
            merged["web_token"] = token
            merged["web_allow_external_access"] = bool(merged.get("web_allow_external_access", False))
            merged["web_auto_start"] = bool(merged.get("web_auto_start", False))
            merged["db_path"] = str(merged.get("db_path", "multi_filter.db"))
            merged["default_action"] = str(merged.get("default_action", "allow")).lower()
            if merged["default_action"] not in {"allow", "silent"}:
                merged["default_action"] = "allow"
            self.config = merged

        db_path = self.config_store.resolve_db_path(self.config.get("db_path", "multi_filter.db"))
        self.group_store = GroupConfigStore(db_path, logger, cache_ttl_seconds=10)
        self.web_manager = WebManager(self.config, self.config_store, self.group_store, logger)

    def _log_config_snapshot(self, stage: str):
        logger.info(
            "[multi_filter][plugin] %s config: web_port=%s web_allow_external_access=%s web_auto_start=%s db_path=%s default_action=%s",
            stage,
            self.config.get("web_port"),
            self.config.get("web_allow_external_access"),
            self.config.get("web_auto_start"),
            self.config.get("db_path"),
            self.config.get("default_action"),
        )

    def _persist_web_auto_start(self, value: bool):
        self.config["web_auto_start"] = bool(value)
        if not self.config_store.save(self.config):
            logger.error("[multi_filter][plugin] 保存 web_auto_start 失败: %s", value)
            return False
        return True

    def _build_management_url(self, with_nonce: bool = False, with_debug: bool = False) -> str:
        port = int(self.config.get("web_port", 8010))
        if bool(self.config.get("web_allow_external_access", False)):
            host = self._detect_primary_ip() or "<服务器IP>"
        else:
            host = "127.0.0.1"
        parts = []
        if with_nonce:
            parts.append(f"v={int(time.time())}")
        if with_debug:
            parts.append("debug=1")
        suffix = f"?{'&'.join(parts)}" if parts else ""
        return f"http://{host}:{port}/{suffix}"

    def _detect_primary_ip(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
            finally:
                sock.close()
        except Exception:
            return ""

    async def initialize(self):
        self.group_store.init_db()
        self.group_store.refresh_cache(force=True)
        self._log_config_snapshot("initialize")

        if bool(self.config.get("web_auto_start", False)):
            self.web_manager.start()
        else:
            logger.info("[multi_filter] 管理页未自动启动，可通过 /开启过滤器管理 启动")

        logger.info("[multi_filter] 插件初始化完成")

    async def terminate(self):
        self.web_manager.stop()
        logger.info("[multi_filter] 插件已终止")

    async def on_message(self, event: AstrMessageEvent):
        try:
            text = get_text(event)

            if not is_group_message(event):
                logger.debug(
                    "[multi_filter][diag] skip: non-group message message_type=%s get_message_type=%s msg_obj.type=%s group_id=%s",
                    getattr(event, "message_type", None),
                    (event.get_message_type() if hasattr(event, "get_message_type") and callable(getattr(event, "get_message_type")) else None),
                    (getattr(getattr(event, "message_obj", None), "type", None)),
                    get_group_id(event),
                )
                return None

            if is_self_message(event):
                logger.debug("[multi_filter][diag] skip: self message")
                return None

            if is_management_command(text):
                logger.debug("[multi_filter][diag] skip: management command text=%s", text)
                return None

            group_id = get_group_id(event)
            user_id = get_user_id(event)
            if not group_id:
                logger.debug("[multi_filter][diag] skip: missing group_id user_id=%s text=%s", user_id, text)
                return None

            cfg = self.group_store.get(group_id)
            if cfg is None:
                cfg = self.group_store.get("__default__")
            if cfg is None:
                logger.debug(
                    "[multi_filter][diag] group_id=%s user_id=%s cfg=NONE default_action=%s",
                    group_id,
                    user_id,
                    self.config.get("default_action", "allow"),
                )
            else:
                logger.debug(
                    "[multi_filter][diag] group_id=%s user_id=%s cfg={enabled=%s whitelist=%d blacklist=%d wake_type=%s wake_mode=%s wake_rules=%d}",
                    group_id,
                    user_id,
                    cfg.enabled,
                    len(cfg.whitelist),
                    len(cfg.blacklist),
                    cfg.wake_type,
                    cfg.wake_mode,
                    len(cfg.wake_rules),
                )

            allowed = should_allow_message(event, cfg, self.config.get("default_action", "allow"))
            logger.debug(
                "[multi_filter][diag] decision group_id=%s user_id=%s allowed=%s text=%s",
                group_id,
                user_id,
                allowed,
                text,
            )

            if allowed:
                return None

            logger.debug("[multi_filter][diag] interrupt group_id=%s user_id=%s", group_id, user_id)
            try:
                event.stop_event()
                logger.debug("[multi_filter][diag] stop_event called group_id=%s user_id=%s", group_id, user_id)
            except Exception as stop_ex:
                logger.error("[multi_filter][diag] stop_event failed: %s", stop_ex)
            return interrupt_result()
        except Exception as ex:
            logger.error("[multi_filter] on_message 处理失败，已放行: %s", ex)
            return None

    async def cmd_start_web(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 开启过滤器管理")
        ok, msg = self.web_manager.start()
        if ok:
            persisted = self._persist_web_auto_start(True)
            fresh_url = self._build_management_url(with_nonce=True)
            access_tip = (
                "请在本机浏览器打开地址并输入 web_token 登录。"
                if not self.config.get("web_allow_external_access", False)
                else "请用浏览器访问服务器 IP 或域名，并输入 web_token 登录。"
            )
            msg = (
                f"管理页已启动: {fresh_url}\n"
                f"{access_tip}"
            )
            if not persisted:
                msg += "\n警告: 自动启动状态保存失败，下次重启可能不会自动开启。"
        else:
            logger.error("[multi_filter][cmd] 开启过滤器管理失败: %s", msg)
        yield event.plain_result(msg if ok else f"开启失败: {msg}")

    async def cmd_stop_web(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 关闭过滤器管理")
        ok, msg = self.web_manager.stop()
        if ok:
            persisted = self._persist_web_auto_start(False)
            if not persisted:
                msg += "（警告: 自动启动状态保存失败）"
        else:
            logger.error("[multi_filter][cmd] 关闭过滤器管理失败: %s", msg)
        yield event.plain_result(msg if ok else f"关闭失败: {msg}")

    async def cmd_web_status(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 过滤器管理状态")
        running = self.web_manager.is_running()
        fresh_url = self._build_management_url(with_nonce=True)
        debug_url = self._build_management_url(with_nonce=True, with_debug=True)
        status = "运行中" if running else "未运行"
        if running:
            access_mode = "外网访问已开启" if bool(self.config.get("web_allow_external_access", False)) else "仅本机访问"
            access_tip = (
                "请在本机浏览器访问并输入 web_token 登录。"
                if not bool(self.config.get("web_allow_external_access", False))
                else "请在可访问服务器的浏览器中输入 web_token 登录。"
            )
            yield event.plain_result(
                f"过滤器管理页状态: {status}（{access_mode}）\n地址: {fresh_url}\n排障地址(debug): {debug_url}\n"
                f"{access_tip}"
            )
            return

        yield event.plain_result(f"过滤器管理页状态: {status}\n可用地址: {fresh_url}")

    async def cmd_set_web_port(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 设置过滤器管理端口")
        text = get_text(event)
        port = extract_port_from_text(text)
        if port is None:
            yield event.plain_result("用法: /设置过滤器管理端口 8010")
            return

        old_port = int(self.config.get("web_port", 8010))
        self.config["web_port"] = port
        saved = self.config_store.save(self.config)
        if not saved:
            self.config["web_port"] = old_port
            logger.error("[multi_filter][cmd] 设置端口失败: 配置保存失败 old=%s new=%s", old_port, port)
            yield event.plain_result("端口更新失败: 配置保存失败")
            return

        was_running = self.web_manager.is_running()
        if was_running:
            self.web_manager.stop()
            started, start_msg = self.web_manager.start()
            if not started:
                self.config["web_port"] = old_port
                self.config_store.save(self.config)
                self.web_manager.start()
                logger.error("[multi_filter][cmd] 设置端口失败: 热重启失败 old=%s new=%s err=%s", old_port, port, start_msg)
                yield event.plain_result(f"端口更新失败: {start_msg}")
                return

        logger.info("[multi_filter][cmd] 端口更新成功 old=%s new=%s restarted=%s", old_port, port, was_running)

        yield event.plain_result(
            f"端口已更新为 {port}" + ("，管理页已重启" if was_running else "，下次开启时生效")
        )
