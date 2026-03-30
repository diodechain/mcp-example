"""
Minimal Diode CLI integration for MCP server.
Join/publish settings are resolved with this precedence (highest wins):

1. **Process environment** — values already in ``os.environ`` when this module loads
   (e.g. ``systemd`` ``Environment=``, launchd ``EnvironmentVariables``, or the shell).
2. **Project ``.env``** — ``<project_root>/.env`` is always read by Python if the file exists;
   only variables *not* already set in ``os.environ`` are filled from the file.
3. **Code defaults** — constants ``_DEFAULT_*`` below (keep aligned with ``.env_example``).

Local MCP listen port and Diode CLI API port are always OS-assigned ephemeral ports.
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

# This package lives at <project>/diode_client/; repo root is the parent.
_diode_client_dir = Path(__file__).parent.resolve()
_project_root = _diode_client_dir.parent
DIODE_CLIENT_DIR = _diode_client_dir

# Defaults when env / project `.env` do not set a value (mirror .env_example).
_DEFAULT_DIODE_JOIN_ADDRESS = ""
_DEFAULT_DIODE_PUBLISH_SCOPE = "public"
_DEFAULT_DIODE_PUBLISH_PORT_STR = "8080"
_DEFAULT_DIODE_PUBLISH_ALLOWLIST = ""


def _load_project_dotenv() -> None:
    """
    Read ``<project_root>/.env`` on every import of this module (no-op if missing).
    For each ``KEY=value``, set ``os.environ[KEY]`` only if ``KEY`` is not already set,
    so launcher/service/plist overrides win over the file. See module docstring for order.
    """
    path = _project_root / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key not in os.environ:
            os.environ[key] = val


_load_project_dotenv()
DIODE_DB_PATH = DIODE_CLIENT_DIR / "diode_mcp.db"
DIODE_LOG_FILE = DIODE_CLIENT_DIR / "diode_client.log"

diode_process: Optional[subprocess.Popen] = None
diode_client_identity: Optional[str] = None
diode_error: Optional[str] = None
diode_output: List[str] = []
diode_config_data: Optional[Dict] = None
_actual_api_port: int = 0
_mcp_local_port: int = 0
_diode_lock = threading.Lock()
_output_lock = threading.Lock()


def diode_join_address_env() -> Optional[str]:
    """If set, Diode runs `join <address>` instead of `publish`."""
    raw = os.environ.get("DIODE_JOIN_ADDRESS", _DEFAULT_DIODE_JOIN_ADDRESS).strip()
    return raw if raw else None


def is_join_mode() -> bool:
    return diode_join_address_env() is not None


def load_publish_scope() -> str:
    """public | protected | private — used only when not in join mode."""
    raw = os.environ.get("DIODE_PUBLISH_SCOPE", _DEFAULT_DIODE_PUBLISH_SCOPE).strip().lower()
    if raw in ("public", "protected", "private"):
        return raw
    return _DEFAULT_DIODE_PUBLISH_SCOPE


def load_publish_perimeter_port() -> int:
    """External perimeter port (local_mcp:this) for publish modes."""
    raw = os.environ.get("DIODE_PUBLISH_PORT", _DEFAULT_DIODE_PUBLISH_PORT_STR).strip()
    try:
        p = int(raw)
        if 1 <= p <= 65535:
            return p
    except (TypeError, ValueError):
        pass
    return int(_DEFAULT_DIODE_PUBLISH_PORT_STR)


def parse_publish_allowlist() -> List[str]:
    """Comma-separated identities for -private publish (trimmed, non-empty)."""
    raw = os.environ.get("DIODE_PUBLISH_ALLOWLIST", _DEFAULT_DIODE_PUBLISH_ALLOWLIST).strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def validate_diode_environment() -> Optional[str]:
    """
    Return an error message if the environment cannot produce a valid Diode command.
    None means OK to attempt start_diode_cli().
    """
    if is_join_mode():
        return None
    if load_publish_scope() == "private" and not parse_publish_allowlist():
        return (
            "DIODE_PUBLISH_SCOPE=private requires DIODE_PUBLISH_ALLOWLIST "
            "(comma-separated Diode addresses, BNS names, etc.)."
        )
    return None


def pick_ephemeral_loopback_port() -> Optional[int]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])
    except OSError:
        return None


def configure_mcp_listen_port(local_mcp_port: int) -> None:
    """Called by server after MCP is bound."""
    global _mcp_local_port
    _mcp_local_port = local_mcp_port


def get_mcp_listen_port() -> int:
    return _mcp_local_port


def find_diode_executable() -> Optional[str]:
    for candidate in (_project_root / "diode", DIODE_CLIENT_DIR / "diode"):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
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
    resolved = Path(diode_path).resolve()
    is_local = diode_path.endswith("diode") and (
        diode_path == "diode"
        or resolved == (_project_root / "diode").resolve()
        or resolved == (DIODE_CLIENT_DIR / "diode").resolve()
    )
    api_addr = f"localhost:{_actual_api_port}"
    log_path = str(DIODE_LOG_FILE)
    db_path = str(DIODE_DB_PATH)
    cmd = [
        diode_path,
        "-debug",
        "-api=true",
        f"-apiaddr={api_addr}",
        f"-dbpath={db_path}",
        f"-logfilepath={log_path}",
    ]
    if is_local:
        cmd.append("-update=false")

    join_addr = diode_join_address_env()
    if join_addr:
        cmd.extend(["join", join_addr])
        return cmd

    if _mcp_local_port <= 0:
        return None

    ext = load_publish_perimeter_port()
    local_ext = f"{_mcp_local_port}:{ext}"
    scope = load_publish_scope()

    if scope == "public":
        cmd.extend(["publish", "-public", local_ext])
    elif scope == "protected":
        cmd.extend(["publish", "-protected", local_ext])
    else:
        parts = parse_publish_allowlist()
        if not parts:
            return None
        cmd.extend(["publish", "-private", local_ext + "," + ",".join(parts)])

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


def _is_port_published_in_config(config: Dict) -> bool:
    if not config or not config.get("client"):
        return False
    if not is_join_mode():
        return True
    perimeter = (config.get("perimeter") or {}) or {}
    props = perimeter.get("properties") or []
    for prop in props:
        if not isinstance(prop, dict):
            continue
        if prop.get("public") or prop.get("private") or prop.get("protected"):
            return True
    return False


def _external_publish_port_from_config(config: Dict) -> Optional[int]:
    if not config:
        return None
    perimeter = (config.get("perimeter") or {}) or {}
    props = perimeter.get("properties") or []
    for prop in props:
        if not isinstance(prop, dict):
            continue
        public_val = prop.get("public")
        if public_val:
            s = str(public_val).strip()
            if ":" in s:
                try:
                    return int(s.rsplit(":", 1)[-1].strip())
                except (TypeError, ValueError):
                    pass
            try:
                return int(s)
            except (TypeError, ValueError):
                pass
        for key in ("private", "protected"):
            v = prop.get(key)
            if v:
                s = str(v).strip()
                if ":" in s:
                    try:
                        return int(s.rsplit(":", 1)[-1].strip())
                    except (TypeError, ValueError):
                        pass
    return None


def get_client_identity() -> Optional[str]:
    _fetch_config()
    return diode_client_identity


def get_published_mcp_urls(config: Optional[Dict] = None) -> List[str]:
    local_port = _mcp_local_port
    local = f"http://127.0.0.1:{local_port}/mcp"
    urls = [local]
    client_id = get_client_identity()
    if not client_id:
        return urls
    cfg = config if config is not None else _fetch_config()
    external = _external_publish_port_from_config(cfg) if cfg else None
    if external is None and not is_join_mode():
        external = load_publish_perimeter_port()
    port = external if external is not None else local_port
    if not is_join_mode():
        urls.append(f"https://{client_id}.diode.link:{port}/mcp")
    elif cfg and _is_port_published_in_config(cfg):
        urls.append(f"https://{client_id}.diode.link:{port}/mcp")
    return urls


def _print_recent_diode_output(lines: int = 30) -> None:
    with _output_lock:
        recent = list(diode_output[-lines:]) if diode_output else []
    if not recent:
        return
    print("  Recent Diode CLI output:", flush=True)
    for line in recent:
        print(f"    {line}", flush=True)


def get_diode_connection_status() -> Dict:
    join_addr = diode_join_address_env()
    if join_addr:
        mode = "join"
    else:
        mode = f"publish:{load_publish_scope()}"
    status = {
        "api_url": get_actual_api_url() if _actual_api_port else None,
        "api_port": _actual_api_port or None,
        "client_identity": get_client_identity(),
        "mode": mode,
        "join_address": join_addr,
        "publish_scope": None if join_addr else load_publish_scope(),
        "mcp_listen_port": _mcp_local_port or None,
        "diode_perimeter_port": None if join_addr else load_publish_perimeter_port(),
        "pid": diode_process.pid if diode_process and diode_process.poll() is None else None,
        "error": diode_error,
    }
    return status


def print_diode_connection_status() -> None:
    s = get_diode_connection_status()
    print("\n" + "=" * 60, flush=True)
    print("Diode connection status", flush=True)
    print("=" * 60, flush=True)
    print(f"  API URL:            {s['api_url'] or '—'}", flush=True)
    print(f"  Diode API port:      {s['api_port'] or '—'} (OS ephemeral)", flush=True)
    print(f"  Client ID:      {s['client_identity'] or '—'}", flush=True)
    print(f"  Mode:           {s['mode']}", flush=True)
    if s.get("join_address"):
        print(f"  Join address:   {s['join_address']}", flush=True)
    if s.get("publish_scope"):
        print(f"  Publish scope:  {s['publish_scope']}", flush=True)
    print(f"  MCP listen:     {s['mcp_listen_port'] or '—'} (local)", flush=True)
    peri = s.get("diode_perimeter_port")
    if peri is not None:
        print(f"  Perimeter port: {peri} (Diode external)", flush=True)
    print(f"  Process PID:    {s['pid'] or '—'}", flush=True)
    if s.get("error"):
        print(f"  Error:          {s['error']}", flush=True)
    print("=" * 60, flush=True)


def start_diode_cli() -> bool:
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
        print(f"⚠ {diode_error}", flush=True)
        return False

    api_port = pick_ephemeral_loopback_port()
    if not api_port:
        diode_error = "Could not obtain an ephemeral port for Diode API"
        print(f"⚠ {diode_error}", flush=True)
        return False

    _actual_api_port = api_port
    DIODE_CLIENT_DIR.mkdir(parents=True, exist_ok=True)
    if not DIODE_LOG_FILE.exists():
        try:
            DIODE_LOG_FILE.touch()
        except Exception:
            pass

    env_err = validate_diode_environment()
    if env_err:
        diode_error = env_err
        print(f"⚠ {env_err}", flush=True)
        return False

    if _mcp_local_port <= 0:
        diode_error = "MCP listen port not set (server must bind before starting Diode)"
        print(f"⚠ {diode_error}", flush=True)
        return False

    cmd = build_diode_command()
    if not cmd:
        diode_error = "Could not build Diode command (check DIODE_* environment variables)"
        print(f"⚠ {diode_error}", flush=True)
        return False

    with _output_lock:
        diode_output.clear()

    stop_tail = threading.Event()

    def tail_log() -> None:
        log_path = DIODE_LOG_FILE
        for _ in range(50):
            if log_path.exists():
                break
            if stop_tail.wait(timeout=0.2):
                return
        if not log_path.exists():
            return
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                while not stop_tail.wait(timeout=0.25):
                    line = f.readline()
                    if not line:
                        continue
                    stripped = line.rstrip()
                    with _output_lock:
                        diode_output.append(stripped)
                        if len(diode_output) > 500:
                            diode_output.pop(0)
                    if stripped:
                        print(f"  diode | {stripped}", flush=True)
        except Exception:
            pass

    try:
        diode_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(DIODE_CLIENT_DIR),
        )

        tail_thread = threading.Thread(target=tail_log, daemon=True)
        tail_thread.start()

        print(f"✓ Diode process started (PID {diode_process.pid})", flush=True)

        waited = 0.0
        api_ready = False
        while waited < 15:
            if diode_process.poll() is not None:
                diode_error = "Diode process exited during startup"
                stop_tail.set()
                print("⚠ Diode CLI: process exited during startup.", flush=True)
                _print_recent_diode_output()
                diode_process = None
                return False
            try:
                req = urllib.request.Request(
                    f"{get_actual_api_url()}/config",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        api_ready = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
            waited += 0.5

        if not api_ready:
            diode_error = "Diode API did not become ready in time (check join address and network)"
            print("⚠ Diode CLI: API did not become ready in time (check join address and network).", flush=True)
            stop_tail.set()
            _print_recent_diode_output()
            if diode_process:
                try:
                    diode_process.terminate()
                    diode_process.wait(timeout=2)
                except Exception:
                    try:
                        diode_process.kill()
                    except Exception:
                        pass
                diode_process = None
            return False

        print("Diode Client auto started, waiting for port to be published...", flush=True)
        publish_ready = False
        published_config = None
        publish_waited = 0.0
        while publish_waited < 20:
            if diode_process.poll() is not None:
                diode_error = "Diode process exited"
                stop_tail.set()
                print("⚠ Diode CLI: process exited while waiting for publish.", flush=True)
                _print_recent_diode_output()
                diode_process = None
                return False
            config = _fetch_config()
            if config and _is_port_published_in_config(config):
                publish_ready = True
                published_config = config
                break
            time.sleep(0.5)
            publish_waited += 0.5

        identity = get_client_identity()
        external_port = _external_publish_port_from_config(published_config) if published_config else None
        if external_port is None and not is_join_mode():
            external_port = load_publish_perimeter_port()
        display_port = external_port if external_port is not None else _mcp_local_port
        if publish_ready and identity:
            print(f"✓ Diode CLI: publishing at {identity}.diode.link:{display_port}", flush=True)
        elif not publish_ready:
            print("⚠ Diode CLI: port not yet published (check perimeter settings).", flush=True)
        print_diode_connection_status()
        if identity and publish_ready:
            urls = get_published_mcp_urls(published_config)
            print("MCP server is published at:", flush=True)
            for u in urls:
                print(f"  {u}", flush=True)
            print("=" * 60 + "\n", flush=True)
        stop_tail.set()
        return True
    except Exception as e:
        diode_error = str(e)
        print(f"⚠ Diode CLI: error starting — {diode_error}", flush=True)
        stop_tail.set()
        _print_recent_diode_output()
        if diode_process:
            try:
                diode_process.terminate()
            except Exception:
                pass
            diode_process = None
        return False


def cleanup_diode() -> None:
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
