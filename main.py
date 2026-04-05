try:
    from .multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin
except ImportError:
    from multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin

from astrbot.api.star import register

MultiFilterPlugin = register(
    "astrbot_plugin_multi_filter",
    "Mxpea",
    "群聊白名单+唤醒条件静音过滤插件",
    "1.0.0",
)(_BaseMultiFilterPlugin)


__all__ = ["MultiFilterPlugin"]
