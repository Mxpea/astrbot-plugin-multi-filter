try:
    from .multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin
except ImportError:
    from multi_filter.plugin import MultiFilterPlugin as _BaseMultiFilterPlugin

from astrbot.api.star import register


@register("astrbot_plugin_multi_filter", "Mxpea", "群聊白名单+唤醒条件静音过滤插件", "1.0.0")
class MultiFilterPlugin(_BaseMultiFilterPlugin):
    pass


__all__ = ["MultiFilterPlugin"]
