from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .config_store import ConfigStore
from .event_logic import (
    extract_port_from_text,
    get_group_id,
    get_text,
    interrupt_result,
    is_group_message,
    is_management_command,
    is_self_message,
    should_allow_message,
)
from .store import GroupConfigStore
from .web import WebManager


@register("multi_filter", "Mxpea", "群聊白名单+唤醒条件静音过滤插件", "1.0.0")
class MultiFilterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._plugin_dir = Path(__file__).resolve().parent.parent

        self.config_store = ConfigStore(self._plugin_dir, logger)
        self.config = self.config_store.load_or_init()

        db_path = self.config_store.resolve_db_path(self.config.get("db_path", "multi_filter.db"))
        self.group_store = GroupConfigStore(db_path, logger, cache_ttl_seconds=10)
        self.web_manager = WebManager(self.config, self.config_store, self.group_store, logger)

    async def initialize(self):
        self.group_store.init_db()
        self.group_store.refresh_cache(force=True)

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
            if not is_group_message(event):
                return None

            if is_self_message(event):
                return None

            if is_management_command(get_text(event)):
                return None

            group_id = get_group_id(event)
            if not group_id:
                return None

            cfg = self.group_store.get(group_id)
            if should_allow_message(event, cfg, self.config.get("default_action", "allow")):
                return None

            return interrupt_result()
        except Exception as ex:
            logger.error("[multi_filter] on_message 处理失败，已放行: %s", ex)
            return None

    @filter.command("开启过滤器管理")
    async def cmd_start_web(self, event: AstrMessageEvent):
        ok, msg = self.web_manager.start()
        if ok:
            self.config["web_auto_start"] = True
            self.config_store.save(self.config)
        yield event.plain_result(msg if ok else f"开启失败: {msg}")

    @filter.command("关闭过滤器管理")
    async def cmd_stop_web(self, event: AstrMessageEvent):
        ok, msg = self.web_manager.stop()
        if ok:
            self.config["web_auto_start"] = False
            self.config_store.save(self.config)
        yield event.plain_result(msg if ok else f"关闭失败: {msg}")

    @filter.command("过滤器管理状态")
    async def cmd_web_status(self, event: AstrMessageEvent):
        running = self.web_manager.is_running()
        port = int(self.config.get("web_port", 8010))
        token = str(self.config.get("web_token", "change-me"))
        status = "运行中" if running else "未运行"
        yield event.plain_result(
            f"过滤器管理页状态: {status}\n端口: {port}\n地址: http://127.0.0.1:{port}/?token={token}"
        )

    @filter.command("设置过滤器管理端口")
    async def cmd_set_web_port(self, event: AstrMessageEvent):
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
                yield event.plain_result(f"端口更新失败: {start_msg}")
                return

        yield event.plain_result(
            f"端口已更新为 {port}" + ("，管理页已重启" if was_running else "，下次开启时生效")
        )
