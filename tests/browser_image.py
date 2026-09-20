"""Native Hermes browser against a loopback fixture; no external accounts."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/opt/hermes")


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b'<h1>Zoen browser check</h1><button onclick="this.textContent=\'confirmed\'">Check</button>')

    def log_message(self, *args):
        return


with tempfile.TemporaryDirectory() as home:
    os.environ["HERMES_HOME"] = home
    from tools.browser_tool import browser_navigate, browser_click, browser_snapshot
    from tools.browser_tool_lifecycle import cleanup_browser
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = browser_navigate(f"http://127.0.0.1:{server.server_port}", task_id="zoen-smoke")
        assert "Zoen browser check" in result, result
        snapshot = browser_snapshot(task_id="zoen-smoke")
        assert 'Check' in snapshot, snapshot
        import re
        match = re.search(r'button.*?ref=(e\d+)', snapshot)
        assert match, snapshot
        browser_click(match.group(1), task_id="zoen-smoke")
        assert "confirmed" in browser_snapshot(task_id="zoen-smoke")
        print(json.dumps({"native_hermes_browser": True, "navigate_snapshot_click": True}))
    finally:
        cleanup_browser("zoen-smoke")
        server.shutdown()
