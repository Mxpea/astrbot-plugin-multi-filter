try:
    from .plugin import MultiFilterPlugin
except Exception:
    MultiFilterPlugin = None

__all__ = ["MultiFilterPlugin"]
