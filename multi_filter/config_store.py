import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG = {
    "web_port": 8010,
    "web_token": "change-me",
    "web_auto_start": False,
    "db_path": "multi_filter.db",
    "default_action": "allow",
}


class ConfigStore:
    def __init__(self, plugin_dir: Path, logger: Any):
        self.plugin_dir = plugin_dir
        self.logger = logger
        self.config_path = self.plugin_dir / "config.json"

    def load_or_init(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            try:
                self.config_path.write_text(
                    json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.logger.info("[multi_filter] 已创建默认配置文件: %s", self.config_path)
            except Exception as ex:
                self.logger.error("[multi_filter] 创建配置文件失败，使用默认配置: %s", ex)
                return dict(DEFAULT_CONFIG)
            return dict(DEFAULT_CONFIG)

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception as ex:
            self.logger.error("[multi_filter] 读取配置失败，使用默认配置: %s", ex)
            data = {}

        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        merged["default_action"] = str(merged.get("default_action", "allow")).lower()
        if merged["default_action"] not in {"allow", "silent"}:
            merged["default_action"] = "allow"
        merged["web_auto_start"] = bool(merged.get("web_auto_start", False))
        return merged

    def save(self, config: Dict[str, Any]) -> bool:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd = None
        temp_path = None
        try:
            temp_fd, temp_raw = tempfile.mkstemp(
                prefix="cfg_", suffix=".json", dir=str(self.config_path.parent)
            )
            temp_path = Path(temp_raw)
            with os.fdopen(temp_fd, "w", encoding="utf-8") as fp:
                json.dump(config, fp, indent=2, ensure_ascii=False)
                fp.flush()
                os.fsync(fp.fileno())
            temp_fd = None
            os.replace(temp_raw, str(self.config_path))
            return True
        except Exception as ex:
            self.logger.error("[multi_filter] 保存配置失败: %s", ex)
            return False
        finally:
            try:
                if temp_fd is not None:
                    try:
                        os.close(temp_fd)
                    except Exception:
                        pass
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def resolve_db_path(self, db_path: str) -> Path:
        p = Path(str(db_path)).expanduser()
        if not p.is_absolute():
            p = (self.plugin_dir / p).resolve()
        return p
