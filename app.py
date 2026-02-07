#!/usr/bin/env python3
import argparse
import http.server
import socketserver
import os
import subprocess
import signal
import time
import random
import threading
import json
from pathlib import Path
# form watchdog.observers import Observer -> PollingObserver for stability in environments with low inotify limits
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

import sys
from pathlib import Path
# Add project root to path to support module imports
PROJECT_ROOT = Path(__file__).parent
sys.path.append(str(PROJECT_ROOT))

from core.utils_security import load_config, resolve_path

# Load security configuration
SEC_CONFIG = load_config()

# Preview configuration
PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = resolve_path(SEC_CONFIG["paths"].get("output_dir", "./dist"))
PORT = 8080

# Directories to watch
WATCH_DIRS = [
    PROJECT_DIR / "posts",
    PROJECT_DIR / "templates",
    PROJECT_DIR / "static",
]

class MyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Set working directory to static output directory
        super().__init__(*args, directory=str(OUTPUT_DIR), **kwargs)

    def do_POST(self):
        if self.path != "/__delete":
            self.send_error(404, "Not Found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body) if body else {}
            filename = payload.get("file", "")
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        if not filename:
            self.send_error(400, "Missing file")
            return

        # Prevent path traversal, only allow relative paths under posts/
        posts_dir = PROJECT_DIR / "posts"
        rel_path = Path(filename)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            self.send_error(400, "Invalid path")
            return

        target = (posts_dir / rel_path).resolve()
        if posts_dir.resolve() not in target.parents:
            self.send_error(400, "Invalid path")
            return

        if not target.exists() or not target.is_file():
            self.send_error(404, "File not found")
            return

        try:
            target.unlink()
        except Exception:
            self.send_error(500, "Failed to delete file")
            return

        # Re-render
        if not ensure_rendered():
            self.send_error(500, "Render failed after delete")
            return

        response = json.dumps({"ok": True, "file": rel_path.as_posix()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

class FileChangeHandler(FileSystemEventHandler):
    """File change listener"""
    def __init__(self):
        self.last_render_time = 0
        self.render_lock = threading.Lock()
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Ignore temporary and hidden files
        if event.src_path.endswith('~') or '/.git/' in event.src_path or '/__pycache__/' in event.src_path:
            return
        
        # Debounce: only render once per second
        current_time = time.time()
        if current_time - self.last_render_time < 1:
            return
        
        with self.render_lock:
            self.last_render_time = current_time
            print(f"\n📝 File changed: {event.src_path}")
            self.render()
    
    def on_created(self, event):
        self.on_modified(event)
    
    def render(self):
        """Run rendering script"""
        try:
            print("🎨 Rendering...")
            result = subprocess.run(
                ['python3', 'tools/render.py'],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print("✅ Render complete! Refresh your browser.")
            else:
                print(f"❌ Render failed: {result.stderr}")
        except Exception as e:
            print(f"❌ Error rendering: {e}")

def kill_process_on_port(port):
    """Kill process occupying specified port"""
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"🔪 Killed process {pid} on port {port}")
                except ProcessLookupError:
                    pass
            time.sleep(1)
            return True
        return False
    except Exception as e:
        print(f"⚠️  Error checking port: {e}")
        return False

def start_file_watcher():
    """Start file watcher"""
    event_handler = FileChangeHandler()
    observer = Observer()
    
    for watch_dir in WATCH_DIRS:
        if watch_dir.exists():
            observer.schedule(event_handler, str(watch_dir), recursive=True)
            print(f"👀 Watching: {watch_dir}")
    
    observer.start()
    return observer

def find_free_port():
    """Find a random free port"""
    return random.randint(8000, 9000)

def start_server(port):
    """Attempt to start server on specified port"""
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("", port), MyHandler)
        return httpd
    except OSError:
        return None

def run_cmd(cmd, cwd=None, label=None):
    if label:
        print(label)
    try:
        result = subprocess.run(cmd, cwd=cwd, text=True)
        if result.returncode != 0:
            print(f"❌ Command failed: {' '.join(cmd)}")
        return result.returncode
    except Exception as e:
        print(f"❌ Command error: {e}")
        return 1

def ensure_rendered():
    return run_cmd(['python3', 'tools/render.py'], cwd=PROJECT_ROOT, label="🎨 Rendering...") == 0

def push_site():
    push_script = PROJECT_DIR / "push"
    push_sh = PROJECT_DIR / "push.sh"

    if push_script.exists():
        return run_cmd(['bash', str(push_script)], cwd=PROJECT_DIR, label="📤 Pushing...") == 0
    if push_sh.exists():
        return run_cmd(['bash', str(push_sh)], cwd=PROJECT_DIR, label="📤 Pushing...") == 0

    # fallback: render then push output repo
    if not ensure_rendered():
        return False
    return run_cmd(
        ['bash', '-lc', 'git add . && git commit -m "Update: $(date +%Y-%m-%d\\ %H:%M)" || true && git push'],
        cwd=OUTPUT_DIR,
        label="📤 Pushing output repo..."
    ) == 0

def main():
    parser = argparse.ArgumentParser(description="Clawtter Dev Server")
    parser.add_argument("-p", "--port", type=int, default=None, help="Server port (default: random free port)")
    parser.add_argument("-push", "--push", action="store_true", help="Render static HTML and push, then exit")
    args = parser.parse_args()

    if args.push:
        success = push_site()
        if success:
            print("✅ Push complete!")
        else:
            print("❌ Push failed!")
        return

    print("🎨 Initial render...")
    if not ensure_rendered():
        return

    httpd = None
    port = args.port

    if port is None:
        # Random port mode (no forced kills)
        for _ in range(10):
            port = find_free_port()
            httpd = start_server(port)
            if httpd:
                print(f"✅ Found free port: {port}")
                break
    else:
        # Fixed port mode (respect user choice)
        print(f"🔍 Checking port {port}...")
        if kill_process_on_port(port):
            print(f"✅ Port {port} is now free")

        max_retries = 3
        for attempt in range(max_retries):
            httpd = start_server(port)
            if httpd:
                break
            if attempt < max_retries - 1:
                print(f"⏳ Port {port} still busy, retrying in 2 seconds... ({attempt + 1}/{max_retries})")
                time.sleep(2)
                kill_process_on_port(port)
    
    if not httpd:
        if port is None:
            print("❌ Failed to start server on any random port!")
        else:
            print(f"❌ Failed to start server on port {port}!")
        return
    
    print(f"\n🚀 Clawtter Development Server")
    print(f"📂 Serving from: {OUTPUT_DIR}")
    print(f"🌐 Local URL: http://localhost:{port}")
    print(f"👀 Auto-reload: ENABLED")
    print(f"💡 Press Ctrl+C to stop\n")
    
    # Start file watching
    observer = start_file_watcher()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Stopping server...")
        observer.stop()
        observer.join()
        httpd.server_close()
        print("✅ Server stopped.")

if __name__ == "__main__":
    main()
