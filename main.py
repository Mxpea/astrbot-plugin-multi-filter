try:
    from .multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin
except ImportError:
    from multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import register


@register("astrbot_plugin_multi_filter", "Mxpea", "群聊白名单+唤醒条件静音过滤插件", "1.0.0")
class MultiFilterPlugin(_BaseMultiFilterPlugin):
    @filter.command_group("过滤器管理")
    def filter_manager(self):
        """过滤器管理命令组:
        开启过滤器管理
        关闭过滤器管理
        过滤器管理状态
        设置过滤器管理端口
        """
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter_manager.command("开启过滤器管理")
    async def cmd_start_web(self, event: AstrMessageEvent):
        yield event.plain_result("🚀 正在启动管理页，请稍等片刻～")
        async for item in super().cmd_start_web(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter_manager.command("关闭过滤器管理")
    async def cmd_stop_web(self, event: AstrMessageEvent):
        async for item in super().cmd_stop_web(event):
            yield item

    @filter_manager.command("过滤器管理状态")
    async def cmd_web_status(self, event: AstrMessageEvent):
        async for item in super().cmd_web_status(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter_manager.command("设置过滤器管理端口")
    async def cmd_set_web_port(self, event: AstrMessageEvent):
        async for item in super().cmd_set_web_port(event):
            yield item


__all__ = ["MultiFilterPlugin"]
