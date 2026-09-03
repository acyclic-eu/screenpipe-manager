#!/usr/bin/env python3
"""
Screenpipe Manager - lightweight local web dashboard.
Controls screenpipe recording (start/stop) and provides search/timeline.
Run: python3 server.py
Open: http://localhost:7654
"""

import http.server
import json
import os
import signal
import socketserver
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

# --- Config ---
PORT = 7654
SCREENPIPE_PORT = 3030

# Find screenpipe binary: env var > local build > PATH > default
import shutil

def find_screenpipe_bin() -> str:
    # 1. Explicit env var
    if bin_path := os.getenv("SCREENPIPE_BIN"):
        return bin_path
    
    # 2. Local build directory (dev mode)
    local_build = os.path.expanduser("~/github/acyclic-eu/screenpipe/target/release/screenpipe")
    if os.path.exists(local_build):
        return local_build
    
    # 3. PATH lookup
    if which_path := shutil.which("screenpipe"):
        return which_path
    
    # 4. Default fallback
    return "/usr/local/bin/screenpipe"

SCREENPIPE_BIN = find_screenpipe_bin()

SCREENPIPE_LOG = "/tmp/screenpipe.log"
API_KEY = None  # fetched at startup
HERE = Path(__file__).parent

def get_api_key():
    """Get the screenpipe API key from the CLI."""
    global API_KEY
    if API_KEY:
        return API_KEY
    try:
        result = subprocess.run(
            [SCREENPIPE_BIN, "auth", "token"],
            capture_output=True, text=True, timeout=5
        )
        key = result.stdout.strip()
        if key.startswith("sp-"):
            API_KEY = key
            return key
    except Exception:
        pass
    # fallback: try secrets db
    try:
        import sqlite3
        conn = sqlite3.connect(str(Path.home() / ".screenpipe" / "secrets.sqlite"))
        cursor = conn.execute("SELECT key FROM secrets WHERE key LIKE 'sp-%' LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            API_KEY = row[0]
            return API_KEY
    except Exception:
        pass
    return None

def screenpipe_running():
    """Check if screenpipe record process is running."""
    try:
        result = subprocess.run(["pgrep", "-f", "screenpipe record"],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False

def screenpipe_health():
    """Get health from screenpipe API."""
    try:
        url = f"http://localhost:{SCREENPIPE_PORT}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def start_screenpipe():
    """Start screenpipe recording."""
    if screenpipe_running():
        return {"status": "already_running"}
    cmd = [SCREENPIPE_BIN, "record", "--port", str(SCREENPIPE_PORT), "--language", "english"]
    subprocess.Popen(cmd, stdout=open(SCREENPIPE_LOG, "a"), stderr=subprocess.STDOUT,
                     start_new_session=True)
    return {"status": "started"}

def stop_screenpipe():
    """Stop screenpipe recording."""
    try:
        result = subprocess.run(["pkill", "-f", "screenpipe record"],
                                capture_output=True, text=True, timeout=5)
        return {"status": "stopped"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def proxy_api(path, query_string):
    """Proxy a request to the screenpipe API with auth header."""
    key = get_api_key()
    url = f"http://localhost:{SCREENPIPE_PORT}{path}"
    if query_string:
        url += f"?{query_string}"
    try:
        req = urllib.request.Request(url)
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "application/json")
            data = resp.read()
            return data, content_type
    except urllib.error.HTTPError as e:
        return json.dumps({"error": str(e)}).encode(), "application/json"
    except Exception as e:
        return json.dumps({"error": str(e), "offline": True}).encode(), "application/json"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = parsed.query

        if path == "/" or path == "/index.html":
            self.serve_file("index.html", "text/html")
        elif path == "/api/status":
            self.send_json({
                "running": bool(screenpipe_running()),
                "health": screenpipe_health(),
                "api_key": get_api_key() is not None,
            })
        elif path == "/api/start":
            self.send_json(start_screenpipe())
        elif path == "/api/stop":
            self.send_json(stop_screenpipe())
        elif path.startswith("/api/frame/"):
            # /api/frame/<frame_id> -> fetch the image from screenpipe and serve it
            frame_id = path.replace("/api/frame/", "")
            self.serve_frame(frame_id)
        elif path.startswith("/api/proxy/"):
            # /api/proxy/search?q=... -> /search?q=...
            sp_path = path.replace("/api/proxy", "", 1)
            data, ct = proxy_api(sp_path, qs)
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def serve_frame(self, frame_id):
        """Serve a frame image by looking up its file path in the DB, or by path query param."""
        # Try query param ?path=<filepath> first
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        file_path = qs.get("path", [None])[0]
        if not file_path:
            # Look up by frame_id in the database
            try:
                import sqlite3 as sql3
                conn = sql3.connect(str(Path.home() / ".screenpipe" / "db.sqlite"))
                cursor = conn.execute(
                    "SELECT name FROM frames WHERE id = ? LIMIT 1", (int(frame_id),)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    file_path = row[0]
            except Exception:
                pass
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    img_data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                self.wfile.write(img_data)
                return
            except Exception as e:
                self.send_error(500, str(e))
                return
        self.send_error(404, "Frame not found")

    def serve_file(self, filename, content_type):
        filepath = HERE / filename
        if filepath.exists():
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def send_json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def main():
    key = get_api_key()
    if not key:
        print("WARNING: Could not find screenpipe API key", file=sys.stderr)
    
    # Auto-start screenpipe if not already running
    if not screenpipe_running():
        print("[Screenpipe] Auto-starting screenpipe...")
        start_screenpipe()
    
    print(f"Screenpipe Manager running at http://localhost:{PORT}")
    print(f"API key: {'found' if key else 'MISSING'}")
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
