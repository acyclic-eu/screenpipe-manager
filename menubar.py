#!/usr/bin/env python3
"""
Screenpipe Manager - macOS menu bar app.
Shows recording status, start/stop control, and opens the web dashboard.
"""

import subprocess
import threading
import time
import json
import urllib.request
import os
import signal
import socketserver
import http.server
from pathlib import Path

import rumps

SCREENPIPE_BIN = "/Users/acyclic/github/acyclic-eu/screenpipe/target/release/screenpipe"
SCREENPIPE_PORT = 3030
SERVER_PORT = 7654
SCREENPIPE_LOG = "/tmp/screenpipe.log"
HERE = Path(__file__).parent
API_KEY = None


def get_api_key():
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
    return None


def screenpipe_running():
    try:
        result = subprocess.run(["pgrep", "-f", "screenpipe record"],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and result.stdout.strip()
    except Exception:
        return False


def screenpipe_health():
    try:
        url = f"http://localhost:{SCREENPIPE_PORT}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def start_screenpipe():
    if screenpipe_running():
        return
    cmd = [SCREENPIPE_BIN, "record", "--port", str(SCREENPIPE_PORT), "--language", "english"]
    subprocess.Popen(cmd, stdout=open(SCREENPIPE_LOG, "a"), stderr=subprocess.STDOUT,
                     start_new_session=True)


def stop_screenpipe():
    try:
        subprocess.run(["pkill", "-f", "screenpipe record"],
                       capture_output=True, text=True, timeout=5)
    except Exception:
        pass


# --- Web server (same as server.py, embedded) ---

class WebHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
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
            start_screenpipe()
            self.send_json({"status": "started"})
        elif path == "/api/stop":
            stop_screenpipe()
            self.send_json({"status": "stopped"})
        elif path.startswith("/api/frame/"):
            file_path = parse_qs(qs).get("path", [None])[0]
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    img_data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                self.wfile.write(img_data)
            else:
                self.send_error(404)
        elif path.startswith("/api/proxy/"):
            sp_path = path.replace("/api/proxy", "", 1)
            key = get_api_key()
            url = f"http://localhost:{SCREENPIPE_PORT}{sp_path}"
            if qs:
                url += f"?{qs}"
            try:
                req = urllib.request.Request(url)
                if key:
                    req.add_header("Authorization", f"Bearer {key}")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ct = resp.headers.get("Content-Type", "application/json")
                    data = resp.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.end_headers()
                    self.wfile.write(data)
            except Exception as e:
                self.send_json({"error": str(e), "offline": True})
        else:
            self.send_error(404)

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


class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_web_server():
    try:
        with ReuseTCPServer(("127.0.0.1", SERVER_PORT), WebHandler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        print(f"Web server error: {e}", flush=True)
        pass  # already running


# --- Menu Bar App ---

class ScreenpipeManagerApp(rumps.App):
    def __init__(self):
        super().__init__(name="Screenpipe Manager", title="🎙", icon=None)
        self.menu = [
            "Start Recording",
            "Stop Recording",
            None,
            "Open Dashboard",
            None,
            "Status",
        ]

    def on_start(self, sender):
        start_screenpipe()
        rumps.notification("Screenpipe", "Recording started", "Screen + audio capture is now active")
        self.refresh_status()

    def on_stop(self, sender):
        stop_screenpipe()
        rumps.notification("Screenpipe", "Recording stopped", "Capture has been stopped")
        self.refresh_status()

    def on_open_dashboard(self, sender):
        subprocess.Popen(["open", "-a", "Firefox", f"http://localhost:{SERVER_PORT}"])

    def on_status(self, sender):
        self.refresh_status()

    @rumps.timer(5)
    def refresh_status(self, sender=None):
        running = screenpipe_running()
        if running:
            self.title = "🎙"
            self.icon = None
            h = screenpipe_health()
            if h:
                meeting = h.get("audio_pipeline", {}).get("meeting_detected", False)
                if meeting:
                    self.title = "🎙📹"
                    self._meeting_notified = True
                else:
                    self._meeting_notified = False
            self.menu["Start Recording"].set_callback(None)
            self.menu["Stop Recording"].set_callback(self.on_stop)
        else:
            self.title = "🎙️̶"
            self.menu["Start Recording"].set_callback(self.on_start)
            self.menu["Stop Recording"].set_callback(None)


if __name__ == "__main__":
    # Auto-start screenpipe before launching the app
    if not screenpipe_running():
        print("[Screenpipe] Auto-starting screenpipe...")
        start_screenpipe()
        time.sleep(2)  # Give it time to start
    
    # Start web server in background thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    time.sleep(0.5)

    app = ScreenpipeManagerApp()
    app.run()
