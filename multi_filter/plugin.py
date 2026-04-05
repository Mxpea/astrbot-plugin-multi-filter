from pathlib import Path
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
            for key in ("web_port", "web_token", "web_auto_start", "db_path", "default_action"):
                if key in external_config:
                    merged[key] = external_config[key]

            try:
                merged["web_port"] = int(merged.get("web_port", 8010))
            except Exception:
                merged["web_port"] = 8010
            merged["web_token"] = str(merged.get("web_token", "change-me")).strip() or "change-me"
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
            "[multi_filter][plugin] %s config: web_port=%s web_auto_start=%s db_path=%s default_action=%s",
            stage,
            self.config.get("web_port"),
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
        token = str(self.config.get("web_token", "change-me"))
        parts = [f"token={token}"]
        if with_nonce:
            parts.append(f"v={int(time.time())}")
        if with_debug:
            parts.append("debug=1")
        return f"http://127.0.0.1:{port}/?" + "&".join(parts)

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
                logger.info("[multi_filter][diag] skip: non-group message")
                return None

            if is_self_message(event):
                logger.info("[multi_filter][diag] skip: self message")
                return None

            if is_management_command(text):
                logger.info("[multi_filter][diag] skip: management command text=%s", text)
                return None

            group_id = get_group_id(event)
            user_id = get_user_id(event)
            if not group_id:
                logger.info("[multi_filter][diag] skip: missing group_id user_id=%s text=%s", user_id, text)
                return None

            cfg = self.group_store.get(group_id)
            if cfg is None:
                logger.info(
                    "[multi_filter][diag] group_id=%s user_id=%s cfg=NONE default_action=%s",
                    group_id,
                    user_id,
                    self.config.get("default_action", "allow"),
                )
            else:
                logger.info(
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
            logger.info(
                "[multi_filter][diag] decision group_id=%s user_id=%s allowed=%s text=%s",
                group_id,
                user_id,
                allowed,
                text,
            )

            if allowed:
                return None

            logger.info("[multi_filter][diag] interrupt group_id=%s user_id=%s", group_id, user_id)
            return interrupt_result()
        except Exception as ex:
            logger.error("[multi_filter] on_message 处理失败，已放行: %s", ex)
            return None

    async def cmd_start_web(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 开启过滤器管理")
        ok, msg = self.web_manager.start()
        if ok:
            self._persist_web_auto_start(True)
            # 附带防缓存参数，避免浏览器命中历史页面脚本。
            fresh_url = self._build_management_url(with_nonce=True)
            msg = f"管理页已启动: {fresh_url}"
        else:
            logger.error("[multi_filter][cmd] 开启过滤器管理失败: %s", msg)
        yield event.plain_result(msg if ok else f"开启失败: {msg}")

    async def cmd_stop_web(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 关闭过滤器管理")
        ok, msg = self.web_manager.stop()
        if ok:
            self._persist_web_auto_start(False)
        else:
            logger.error("[multi_filter][cmd] 关闭过滤器管理失败: %s", msg)
        yield event.plain_result(msg if ok else f"关闭失败: {msg}")

    async def cmd_web_status(self, event: AstrMessageEvent):
        logger.info("[multi_filter][cmd] 收到命令: 过滤器管理状态")
        running = self.web_manager.is_running()
        fresh_url = self._build_management_url(with_nonce=True)
        debug_url = self._build_management_url(with_nonce=True, with_debug=True)
        status = "运行中" if running else "未运行"
        yield event.plain_result(
            f"过滤器管理页状态: {status}\n地址: {fresh_url}\n排障地址(debug): {debug_url}"
        )

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
