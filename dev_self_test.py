"""Standalone local self-test for multi_filter.

This script runs without AstrBot installed by injecting minimal stub modules
into sys.modules before importing the plugin package.

It verifies:
- SQLite schema initialization and persistence
- Blacklist / whitelist / wake rule logic
- Web API CRUD behavior
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.request import ProxyHandler, Request, build_opener


def install_astrbot_stubs() -> None:
    if "astrbot" in sys.modules:
        return

    astrbot = ModuleType("astrbot")
    api = ModuleType("astrbot.api")
    event = ModuleType("astrbot.api.event")
    star = ModuleType("astrbot.api.star")

    class _Logger:
        def info(self, *args: Any, **kwargs: Any) -> None:
            print("[INFO]", *args)

        def error(self, *args: Any, **kwargs: Any) -> None:
            print("[ERROR]", *args)

        def debug(self, *args: Any, **kwargs: Any) -> None:
            print("[DEBUG]", *args)

    def _filter_command(_: str):
        def decorator(func):
            return func

        return decorator

    class _MessageEventResult:
        @staticmethod
        def interrupt():
            return SimpleNamespace(kind="interrupt")

        @staticmethod
        def stop():
            return SimpleNamespace(kind="stop")

        @staticmethod
        def block():
            return SimpleNamespace(kind="block")

    class _Context:
        pass

    class _Star:
        def __init__(self, context):
            self.context = context

    def _register(*args: Any, **kwargs: Any):
        def decorator(cls):
            return cls

        return decorator

    setattr(event, "AstrMessageEvent", object)
    setattr(event, "MessageEventResult", _MessageEventResult)
    setattr(event, "filter", SimpleNamespace(command=_filter_command))
    setattr(star, "Context", _Context)
    setattr(star, "Star", _Star)
    setattr(star, "register", _register)
    setattr(api, "logger", _Logger())
    setattr(astrbot, "api", api)

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star


@dataclass
class FakeSegment:
    qq: str


class FakeEvent:
    def __init__(
        self,
        group_id: str,
        sender_id: str,
        message_str: str,
        self_id: str = "99999",
        at_bot: bool = False,
    ):
        self.group_id = group_id
        self.sender_id = sender_id
        self.message_str = message_str
        self.self_id = self_id
        self._at_bot = at_bot

    def is_group(self):
        return True

    def get_messages(self):
        return [FakeSegment(qq=self.self_id)] if self._at_bot else []

    def plain_result(self, text: str):
        return text


def http_json(url: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    opener = build_opener(ProxyHandler({}))
    with opener.open(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LocalLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        print("[INFO]", *args)

    def error(self, *args: Any, **kwargs: Any) -> None:
        print("[ERROR]", *args)

    def debug(self, *args: Any, **kwargs: Any) -> None:
        print("[DEBUG]", *args)


def main() -> int:
    install_astrbot_stubs()

    from multi_filter.config_store import ConfigStore
    from multi_filter.models import GroupConfig
    from multi_filter.store import GroupConfigStore
    from multi_filter.web import WebManager
    from multi_filter.event_logic import should_allow_message, interrupt_result

    logger = LocalLogger()

    root = Path(__file__).resolve().parent

    with tempfile.TemporaryDirectory(prefix="mf_test_") as tmpdir:
        tmp = Path(tmpdir)
        config_store = ConfigStore(tmp, logger)
        config = {
            "web_port": 18010,
            "web_token": "test-token",
            "web_auto_start": False,
            "db_path": str(tmp / "multi_filter.db"),
            "default_action": "allow",
        }
        if not config_store.save(config):
            raise RuntimeError("failed to save test config")

        store = GroupConfigStore(tmp / "multi_filter.db", logger, cache_ttl_seconds=1)
        store.init_db()
        store.refresh_cache(force=True)

        cfg = GroupConfig(
            group_id="123456",
            enabled=True,
            whitelist=["10001"],
            blacklist=["20001"],
            wake_type="always",
            wake_value="",
            wake_mode="any",
            wake_rules=[{"type": "keyword", "value": ["帮助"]}, {"type": "prefix", "value": "/"}],
        )
        store.upsert(cfg)

        loaded = store.get("123456")
        assert loaded is not None, "group config should be persisted"
        assert loaded.blacklist == ["20001"], loaded
        assert loaded.wake_mode == "any", loaded
        assert len(loaded.wake_rules) == 2, loaded

        allow_event = FakeEvent("123456", "10001", "/help")
        deny_event = FakeEvent("123456", "10001", "no wake")
        black_event = FakeEvent("123456", "20001", "/help")

        assert should_allow_message(allow_event, loaded, "allow") is True, "wake rule should pass"
        assert should_allow_message(deny_event, loaded, "allow") is False, "missing wake should block"
        assert should_allow_message(black_event, loaded, "allow") is False, "blacklist should block"
        assert interrupt_result() is not None, "interrupt helper should return a result"

        manager = WebManager(config, config_store, store, logger)
        ok, msg = manager.start()
        assert ok, msg

        try:
            time.sleep(0.3)
            base = "http://127.0.0.1:18010"
            settings = http_json(f"{base}/api/settings?token=test-token")
            assert settings["ok"] is True
            assert settings["settings"]["web_port"] == 18010

            groups = http_json(f"{base}/api/groups?token=test-token")
            assert groups["ok"] is True
            assert "123456" in groups["groups"]

            detail = http_json(f"{base}/api/group?group_id=123456&token=test-token")
            assert detail["ok"] is True
            assert detail["group"]["blacklist"] == ["20001"]

            update = http_json(
                f"{base}/api/group?token=test-token",
                method="POST",
                body={
                    "group_id": "123456",
                    "enabled": True,
                    "whitelist": ["10001"],
                    "blacklist": ["20001", "20002"],
                    "wake_type": "prefix",
                    "wake_value": "/",
                    "wake_mode": "all",
                    "wake_rules": [
                        {"type": "prefix", "value": "/"},
                        {"type": "keyword", "value": ["帮助"]},
                    ],
                },
            )
            assert update["ok"] is True

            detail2 = http_json(f"{base}/api/group?group_id=123456&token=test-token")
            assert detail2["group"]["blacklist"] == ["20001", "20002"]
            assert detail2["group"]["wake_mode"] == "all"
        finally:
            manager.stop()

        # Re-open database directly to verify persistence is on disk.
        conn = sqlite3.connect(str(tmp / "multi_filter.db"))
        try:
            row = conn.execute(
                "SELECT group_id, blacklist, wake_mode, wake_rules FROM group_config WHERE group_id=?",
                ("123456",),
            ).fetchone()
            assert row is not None, "sqlite row should exist"
            assert json.loads(row[1]) == ["20001", "20002"]
            assert row[2] == "all"
            assert len(json.loads(row[3])) == 2
        finally:
            conn.close()

        print("All local self-tests passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())