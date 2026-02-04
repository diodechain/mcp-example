"""
Minimal Diode CLI integration for MCP server.
Spawns Diode CLI to publish the MCP server's port publicly (https://<client>.diode.link:PORT/mcp).
"""
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Dict, List

# Diode API port (CLI's local API), not the MCP server port
DIODE_API_PORT = 60401
DIODE_DB_PATH = "diode_mcp.db"
DEFAULT_JOIN_ADDRESS = "0x0000000000000000000000000000000000000000"

_base_dir = Path(__file__).parent.absolute()
DIODE_LOG_FILE = _base_dir / "diode_client.log"

diode_process: Optional[subprocess.Popen] = None
diode_client_identity: Optional[str] = None
diode_error: Optional[str] = None
diode_output: List[str] = []
diode_config_data: Optional[Dict] = None
_actual_api_port = DIODE_API_PORT
_publish_port: int = 8099  # MCP server port to publish
_diode_lock = threading.Lock()
_output_lock = threading.Lock()


def get_config_path() -> Path:
    return Path(__file__).parent / "config.json"


def load_diode_join_address() -> str:
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                if config and "join_address" in config:
                    return config["join_address"]
        except Exception:
            pass
    return DEFAULT_JOIN_ADDRESS


def set_publish_port(port: int):
    """Set the port to publish (MCP server port)."""
    global _publish_port
    _publish_port = port


def get_publish_port() -> int:
    return _publish_port


def find_free_port(start_port: int, max_attempts: int = 100) -> Optional[int]:
    for i in range(max_attempts):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def find_diode_executable() -> Optional[str]:
    if os.path.exists("./diode") and os.access("./diode", os.X_OK):
        return "./diode"
    import shutil
    path = shutil.which("diode")
    if path:
        return path
    for p in [
        os.path.expanduser("~/opt/diode/diode"),
        "/usr/local/bin/diode",
        "/usr/bin/diode",
        os.path.expanduser("~/bin/diode"),
    ]:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


def get_actual_api_url() -> str:
    return f"http://localhost:{_actual_api_port}"


def build_diode_command() -> Optional[list]:
    diode_path = find_diode_executable()
    if not diode_path:
        return None
    is_local = diode_path in ("./diode", "diode")
    join_address = load_diode_join_address()
    api_addr = f"localhost:{_actual_api_port}"
    log_path = str(DIODE_LOG_FILE)
    cmd = [
        diode_path,
        "-debug",
        "-api=true",
        f"-apiaddr={api_addr}",
        f"-dbpath={DIODE_DB_PATH}",
        f"-logfilepath={log_path}",
    ]
    if is_local:
        cmd.append("-update=false")
    if join_address == DEFAULT_JOIN_ADDRESS:
        cmd.extend(["publish", "-public", f"{_publish_port}:{_publish_port}"])
    else:
        cmd.extend(["join", join_address])
    return cmd


def _fetch_config() -> Optional[Dict]:
    global diode_config_data, diode_client_identity, diode_error
    if diode_process is None or diode_process.poll() is not None:
        diode_error = "Diode process is not running"
        diode_config_data = None
        return None
    url = f"{get_actual_api_url()}/config"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status != 200:
                    continue
                data = json.loads(resp.read().decode())
                if data.get("success") and "config" in data:
                    config = data["config"]
                    diode_config_data = config
                    cid = config.get("client")
                    if cid:
                        diode_client_identity = cid
                        diode_error = None
                    return config
        except Exception as e:
            diode_error = str(e)
            if attempt < 4:
                time.sleep(0.5)
            else:
                diode_config_data = None
                return None
    return None


def get_client_identity() -> Optional[str]:
    _fetch_config()
    return diode_client_identity


def get_published_mcp_urls() -> List[str]:
    """Return local and public MCP URLs (with /mcp path)."""
    port = _publish_port
    local = f"http://127.0.0.1:{port}/mcp"
    urls = [local]
    client_id = get_client_identity()
    if client_id and load_diode_join_address() == DEFAULT_JOIN_ADDRESS:
        urls.append(f"https://{client_id}.diode.link:{port}/mcp")
    return urls


def start_diode_cli() -> bool:
    """Start Diode CLI publishing the configured port. Returns True if started (or already running)."""
    global diode_process, diode_error, _actual_api_port

    with _diode_lock:
        if diode_process is not None and diode_process.poll() is None:
            identity = get_client_identity()
            if identity:
                return True
            try:
                diode_process.terminate()
                diode_process.wait(timeout=2)
            except Exception:
                try:
                    diode_process.kill()
                except Exception:
                    pass
            diode_process = None

    path = find_diode_executable()
    if not path:
        diode_error = "Diode executable not found. Install from https://diode.io/download/#cli"
        print(f"⚠ {diode_error}")
        return False

    free_port = find_free_port(DIODE_API_PORT)
    if not free_port:
        diode_error = f"No free port from {DIODE_API_PORT}"
        print(f"⚠ {diode_error}")
        return False

    _actual_api_port = free_port
    if not DIODE_LOG_FILE.exists():
        try:
            DIODE_LOG_FILE.touch()
        except Exception:
            pass

    cmd = build_diode_command()
    if not cmd:
        diode_error = "Could not build Diode command"
        print(f"⚠ {diode_error}")
        return False

    with _output_lock:
        diode_output.clear()

    try:
        diode_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def read_out():
            if diode_process and diode_process.stdout:
                try:
                    for line in iter(diode_process.stdout.readline, ""):
                        if not line:
                            break
                        with _output_lock:
                            diode_output.append(line.rstrip())
                            if len(diode_output) > 500:
                                diode_output.pop(0)
                except Exception:
                    pass

        t = threading.Thread(target=read_out, daemon=True)
        t.start()

        print(f"✓ Diode process started (PID {diode_process.pid}), publishing port {_publish_port}")

        waited = 0
        while waited < 15:
            if diode_process.poll() is not None:
                diode_error = "Diode process exited during startup"
                diode_process = None
                return False
            try:
                req = urllib.request.Request(
                    f"{get_actual_api_url()}/config",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
            time.sleep(0.5)
            waited += 0.5

        identity = get_client_identity()
        if identity:
            urls = get_published_mcp_urls()
            print("\n" + "=" * 60)
            print("MCP server is published at:")
            for u in urls:
                print(f"  {u}")
            print("=" * 60 + "\n")
        return True
    except Exception as e:
        diode_error = str(e)
        print(f"⚠ Error starting Diode: {diode_error}")
        if diode_process:
            try:
                diode_process.terminate()
            except Exception:
                pass
            diode_process = None
        return False


def cleanup_diode():
    global diode_process
    if diode_process is not None:
        try:
            diode_process.terminate()
            diode_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                diode_process.kill()
            except Exception:
                pass
        except Exception:
            pass
        diode_process = None
