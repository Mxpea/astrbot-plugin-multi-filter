import os
import json
import sqlite3
import time
from types import SimpleNamespace
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from dataclasses import asdict

class DummyContext: pass
class DummyEvent:
    def __init__(self, is_group=True, group_id="12345", text="test", sender_id="user1"):
        self._is_group = is_group
        self._group_id = group_id
        self._text = text
        self._sender_id = sender_id
        
        # 兼容 AstrBot API 的 mock
        self.session = SimpleNamespace(session_id=group_id)
        self.message_obj = SimpleNamespace(
            group_id=group_id,
            sender=SimpleNamespace(user_id=sender_id),
            message=[{'type': 'text', 'text': text}],
        )

    def get_message_str(self): return self._text

def main():
    print("Testing pure UI refactor...")
    
    from multi_filter.store import GroupConfigStore
    from multi_filter.models import GroupConfig
    
    # 1. Start Server
    from multi_filter.web import WebManager
    import tempfile
    from pathlib import Path
    
    d = tempfile.mkdtemp()
    db_path = Path(d) / "test.db"
    
    class DummyLogger:
        def info(self, msg, *args): print("[INFO]", msg % args if args else msg)
        def error(self, msg, *args): print("[ERROR]", msg % args if args else msg)
    
    store = GroupConfigStore(db_path, DummyLogger())
    store.init_db()
    
    cfg = {"web_port": 18010, "web_token": "test-token"}
    class DummyConfigStore:
        def load_or_init(self): return cfg
        
    web = WebManager(cfg, DummyConfigStore(), store, DummyLogger())
    web.start()
    
    time.sleep(0.5)
    
    base = "http://127.0.0.1:18010/"
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    login_data = urllib.parse.urlencode({"token": "test-token"}).encode('utf-8')
    login_req = urllib.request.Request(base + "?op=login", data=login_data, method="POST")
    opener.open(login_req, timeout=5).read()

    resp = opener.open(base, timeout=5).read().decode('utf-8')
    assert 'AstrBot 群聊过滤器管理' in resp
    assert '暂无群配置' in resp
    
    # 2. Add Group via POST
    print("Testing Add Group POST...")
    data = urllib.parse.urlencode({"group_id": "test_grp"}).encode('utf-8')
    req = urllib.request.Request(base + "?op=add", data=data, method="POST")
    try: opener.open(req, timeout=5)
    except urllib.error.HTTPError as e: print("Expected Redirections, fine", e.code)
    except Exception: pass
    
    time.sleep(0.5)
    
    # Verify group is added in HTML
    resp = opener.open(base, timeout=5).read().decode('utf-8')
    assert 'test_grp' in resp
    print("Test passed! Server correctly returned HTML string")
    web.stop()

if __name__ == "__main__":
    main()
