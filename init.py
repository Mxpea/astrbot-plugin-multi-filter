from pathlib import Path


def init_plugin(plugin_dir: str | Path | None = None) -> bool:
    if plugin_dir is not None:
        Path(plugin_dir).mkdir(parents=True, exist_ok=True)
    return True
