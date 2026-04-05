import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Dict


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _default_config() -> Dict[str, Any]:
    return {
        "web_port": 8010,
        "web_token": _generate_token(),
        "web_allow_external_access": False,
        "web_auto_start": False,
        "db_path": "multi_filter.db",
        "default_action": "allow",
    }


DEFAULT_CONFIG = _default_config()


class ConfigStore:
    def __init__(self, plugin_dir: Path, logger: Any):
        self.plugin_dir = plugin_dir
        self.logger = logger
        self.data_dir = self._resolve_data_dir()
        self.config_path = self.data_dir / "config.json"
        self.backup_config_path = self.data_dir / "config.backup.json"

    def _resolve_data_dir(self) -> Path:
        plugin_name = "astrbot_plugin_multi_filter"

        # AstrBot 标准目录（用户级持久化目录）
        home_based = Path.home() / ".astrbot" / "data" / "plugins" / plugin_name

        # 如果插件本身已位于 data/plugins 下，继续沿用当前目录。
        normalized = str(self.plugin_dir).replace("\\", "/").lower()
        if "/data/plugins/" in normalized:
            return self.plugin_dir

        # 兼容通过环境变量覆盖（可选）。
        env_data_root = os.getenv("ASTRBOT_DATA_DIR", "").strip()
        if env_data_root:
            return Path(env_data_root).expanduser().resolve() / "plugins" / plugin_name

        return home_based

    def _migrate_if_needed(self):
        # 从旧路径迁移到新持久化目录，避免更新插件后丢配置。
        legacy_cfg = self.plugin_dir / "config.json"
        legacy_db = self.plugin_dir / "multi_filter.db"
        new_cfg = self.config_path
        new_db = self.data_dir / "multi_filter.db"

        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            self.logger.error("[multi_filter] 创建持久化目录失败，继续使用当前路径: %s", ex)
            return

        try:
            if (not new_cfg.exists()) and legacy_cfg.exists() and legacy_cfg != new_cfg:
                new_cfg.write_text(legacy_cfg.read_text(encoding="utf-8"), encoding="utf-8")
                self.logger.info("[multi_filter] 已迁移配置文件到持久化目录: %s", new_cfg)
            if (not self.backup_config_path.exists()) and new_cfg.exists():
                self.backup_config_path.write_text(new_cfg.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as ex:
            self.logger.error("[multi_filter] 迁移配置文件失败: %s", ex)

        try:
            if (not new_db.exists()) and legacy_db.exists() and legacy_db != new_db:
                new_db.write_bytes(legacy_db.read_bytes())
                self.logger.info("[multi_filter] 已迁移数据库到持久化目录: %s", new_db)
        except Exception as ex:
            self.logger.error("[multi_filter] 迁移数据库失败: %s", ex)

    def load_or_init(self) -> Dict[str, Any]:
        self._migrate_if_needed()

        if not self.config_path.exists():
            if self.backup_config_path.exists():
                try:
                    self.config_path.parent.mkdir(parents=True, exist_ok=True)
                    restored = self.backup_config_path.read_text(encoding="utf-8")
                    self.config_path.write_text(restored, encoding="utf-8")
                    self.logger.info("[multi_filter] 已从备份恢复配置文件: %s", self.config_path)
                except Exception as ex:
                    self.logger.error("[multi_filter] 从备份恢复配置失败: %s", ex)

        if not self.config_path.exists():
            created = _default_config()
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_path.write_text(
                    json.dumps(created, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                self.logger.info("[multi_filter] 已创建默认配置文件: %s", self.config_path)
            except Exception as ex:
                self.logger.error("[multi_filter] 创建配置文件失败，使用默认配置: %s", ex)
                return dict(created)
            return dict(created)

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception as ex:
            self.logger.error("[multi_filter] 读取配置失败，使用默认配置: %s", ex)
            data = {}
            if self.backup_config_path.exists():
                try:
                    backup_data = json.loads(self.backup_config_path.read_text(encoding="utf-8"))
                    if isinstance(backup_data, dict):
                        data = backup_data
                        self.logger.info("[multi_filter] 已从备份配置恢复设置")
                except Exception as backup_ex:
                    self.logger.error("[multi_filter] 读取备份配置失败: %s", backup_ex)

        if not data and self.backup_config_path.exists():
            try:
                backup_data = json.loads(self.backup_config_path.read_text(encoding="utf-8"))
                if isinstance(backup_data, dict):
                    data = backup_data
                    self.logger.info("[multi_filter] 已从备份配置恢复空配置")
            except Exception as backup_ex:
                self.logger.error("[multi_filter] 读取备份配置失败: %s", backup_ex)

        merged = _default_config()
        merged.update(data)
        merged["default_action"] = str(merged.get("default_action", "allow")).lower()
        if merged["default_action"] not in {"allow", "silent"}:
            merged["default_action"] = "allow"
        merged["web_auto_start"] = bool(merged.get("web_auto_start", False))
        merged["web_allow_external_access"] = bool(merged.get("web_allow_external_access", False))

        token = str(merged.get("web_token", "")).strip()
        if (not token) or token == "change-me":
            merged["web_token"] = _generate_token()
            if self.save(merged):
                self.logger.warning("[multi_filter] 检测到弱 token，已自动生成新的随机 token。")
            else:
                self.logger.error("[multi_filter] 自动修复 token 失败，请手动更新 web_token。")
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
            self.backup_config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
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
            p = (self.data_dir / p).resolve()
        return p
