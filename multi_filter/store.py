import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import GroupConfig


class GroupConfigStore:
    def __init__(self, db_path: Path, logger: Any, cache_ttl_seconds: int = 10):
        self.db_path = db_path
        self.logger = logger

        self._db_lock = threading.RLock()
        self._cache_lock = threading.RLock()

        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_expire_at = 0.0
        self._group_cache: Dict[str, GroupConfig] = {}

    def _db_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db_lock:
            conn = self._db_conn()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS group_config (
                        group_id TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        whitelist TEXT NOT NULL DEFAULT '[]',
                        blacklist TEXT NOT NULL DEFAULT '[]',
                        wake_type TEXT NOT NULL DEFAULT 'always',
                        wake_value TEXT NOT NULL DEFAULT '',
                        wake_mode TEXT NOT NULL DEFAULT 'any',
                        wake_rules TEXT NOT NULL DEFAULT '[]'
                    )
                    """
                )

                # 兼容历史版本数据库，自动补齐新字段。
                cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(group_config)").fetchall()
                }
                if "blacklist" not in cols:
                    conn.execute("ALTER TABLE group_config ADD COLUMN blacklist TEXT NOT NULL DEFAULT '[]'")
                if "wake_mode" not in cols:
                    conn.execute("ALTER TABLE group_config ADD COLUMN wake_mode TEXT NOT NULL DEFAULT 'any'")
                if "wake_rules" not in cols:
                    conn.execute("ALTER TABLE group_config ADD COLUMN wake_rules TEXT NOT NULL DEFAULT '[]'")

                conn.commit()
                self.logger.info("[multi_filter] 数据库初始化完成: %s", self.db_path)
            finally:
                conn.close()

    def refresh_cache(self, force: bool = False):
        now = time.time()
        with self._cache_lock:
            if not force and now < self._cache_expire_at:
                return

        with self._db_lock:
            conn = self._db_conn()
            try:
                rows = conn.execute(
                    "SELECT group_id, enabled, whitelist, blacklist, wake_type, wake_value, wake_mode, wake_rules FROM group_config"
                ).fetchall()
            except Exception as ex:
                self.logger.error("[multi_filter] 刷新缓存读取数据库失败: %s", ex)
                return
            finally:
                conn.close()

        new_cache: Dict[str, GroupConfig] = {}
        for row in rows:
            try:
                cfg = GroupConfig.from_row(row)
                new_cache[cfg.group_id] = cfg
            except Exception as ex:
                self.logger.error("[multi_filter] 解析群配置失败: %s", ex)

        with self._cache_lock:
            self._group_cache = new_cache
            self._cache_expire_at = time.time() + self._cache_ttl_seconds

    def get(self, group_id: str) -> Optional[GroupConfig]:
        self.refresh_cache(force=False)
        with self._cache_lock:
            return self._group_cache.get(group_id)

    def list_groups(self) -> List[str]:
        self.refresh_cache(force=False)
        with self._cache_lock:
            return sorted(self._group_cache.keys())

    def upsert(self, cfg: GroupConfig):
        with self._db_lock:
            conn = self._db_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO group_config (
                        group_id,
                        enabled,
                        whitelist,
                        blacklist,
                        wake_type,
                        wake_value,
                        wake_mode,
                        wake_rules
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(group_id) DO UPDATE SET
                        enabled=excluded.enabled,
                        whitelist=excluded.whitelist,
                        blacklist=excluded.blacklist,
                        wake_type=excluded.wake_type,
                        wake_value=excluded.wake_value,
                        wake_mode=excluded.wake_mode,
                        wake_rules=excluded.wake_rules
                    """,
                    cfg.to_db_tuple(),
                )
                conn.commit()
            finally:
                conn.close()

        with self._cache_lock:
            self._group_cache[cfg.group_id] = cfg
            self._cache_expire_at = time.time() + self._cache_ttl_seconds

    def delete(self, group_id: str):
        with self._db_lock:
            conn = self._db_conn()
            try:
                conn.execute("DELETE FROM group_config WHERE group_id=?", (group_id,))
                conn.commit()
            finally:
                conn.close()

        with self._cache_lock:
            self._group_cache.pop(group_id, None)
            self._cache_expire_at = time.time() + self._cache_ttl_seconds
