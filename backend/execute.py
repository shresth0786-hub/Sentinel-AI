"""
Sentinel AI — one-file launcher.

Runs the whole program with a single command, with no dependency on any
other helper file (no VS Code tasks, no PowerShell script, no .env editing):

    python execute.py                # auto: Docker stack if available, else local
    python execute.py --mode docker  # full stack: app + PostgreSQL + Redis
    python execute.py --mode local   # backend + Vite dashboard on this machine
    python execute.py --stop         # stop a running Docker stack

Docker mode  -> starts the hardened 3-service stack, waits until the API is
                healthy, opens the dashboard, and leaves the stack running
                when you close it (stop it with `--stop`).
Local mode   -> starts the FastAPI backend and the Vite dev server as child
                processes, opens the dashboard, and stops both on Ctrl+C.

Only the Python standard library is used, so this runs on any machine that
already has Python — nothing to pip install.

This file lives in backend/ with the rest of the code; it locates the
project root automatically, so it works from anywhere.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


# --------------------------------------------------------------------------- paths
def _find_project_root(start: Path) -> Path:
    """Walk up from this file until the folder that holds the project is found."""
    for candidate in [start, *start.parents]:
        if (candidate / "docker-compose.yml").is_file() and (candidate / "backend").is_dir():
            return candidate
    return start.parent


_HERE = Path(__file__).resolve().parent
ROOT = _find_project_root(_HERE)
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend" / "app"
COMPOSE_FILE = ROOT / "docker-compose.yml"

API_PORT = 8100
UI_PORT = 5173
API_URL = f"http://127.0.0.1:{API_PORT}"
UI_URL = f"http://localhost:{UI_PORT}"
DASHBOARD_URL = f"http://localhost:{API_PORT}"

# Development defaults so the launcher works with zero setup. Override them by
# exporting the same environment variables (or using a .env file) before running.
DEV_POSTGRES_PASSWORD = "sentinel-db-pw-2026"
DEV_AUTH_SECRET = "0" * 62 + "ff"
DEV_ADMIN_PASSWORD = "SentinelAdmin!2026"

# Standard install locations, so the launcher works from a fresh shell where
# Docker's bin folder is not on PATH yet.
DOCKER_BIN_DIRS = [
    Path(r"C:\Program Files\Docker\Docker\resources\bin"),
    Path("/usr/local/bin"),
    Path("/Applications/Docker.app/Contents/Resources/bin"),
]
DOCKER_DESKTOP_EXE = [
    Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
    Path("/Applications/Docker.app/Contents/MacOS/Docker"),
]


def log(msg: str = "") -> None:
    print(f"[sentinel] {msg}", flush=True)


def ensure_docker_on_path() -> None:
    """Add Docker's bin folder to PATH if the CLI is not already reachable."""
    if have("docker"):
        return
    for folder in DOCKER_BIN_DIRS:
        exe = folder / ("docker.exe" if os.name == "nt" else "docker")
        if exe.is_file():
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
            log(f"added {folder} to PATH")
            return


def start_docker_desktop() -> bool:
    """Launch Docker Desktop and wait for the engine to answer.

    The process is started detached so that Docker Desktop keeps running even
    if this launcher is closed or killed.
    """
    ensure_docker_on_path()
    for exe in DOCKER_DESKTOP_EXE:
        if exe.is_file():
            log("Docker Desktop is not running - starting it ...")
            kwargs: dict = {}
            if os.name == "nt":
                # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
                # The last flag detaches it from any job object (e.g. a CI runner or
                # a shell that kills its process tree), so Docker Desktop survives
                # even if this launcher is closed.
                flags = 0x00000008 | 0x00000200 | 0x01000000
                try:
                    subprocess.Popen([str(exe)], cwd=str(exe.parent),
                                     creationflags=flags)
                except OSError:
                    subprocess.Popen([str(exe)], cwd=str(exe.parent),
                                     creationflags=0x00000008 | 0x00000200)
            else:
                kwargs["start_new_session"] = True
                subprocess.Popen([str(exe)], cwd=str(exe.parent), **kwargs)
            deadline = time.time() + 240
            while time.time() < deadline:
                if docker_daemon_ready():
                    log("Docker engine is ready")
                    return True
                time.sleep(3.0)
            log("ERROR: the Docker engine did not start in time")
            return False
    return False


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# --------------------------------------------------------------------------- helpers
def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for_http(url: str, timeout: float, label: str) -> bool:
    """Poll a URL until it answers 200 or the timeout expires."""
    log(f"waiting for {label} ({url}) ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(url):
            log(f"{label} is up")
            return True
        time.sleep(1.0)
    log(f"ERROR: {label} did not come up within {int(timeout)}s")
    return False


def docker_daemon_ready() -> bool:
    if not have("docker"):
        return False
    try:
        out = subprocess.run(["docker", "info"], capture_output=True, timeout=25)
        return out.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def image_exists(name: str) -> bool:
    try:
        out = subprocess.run(["docker", "images", "-q", name],
                             capture_output=True, text=True, timeout=30)
        return bool(out.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        return False


def apply_dev_env() -> None:
    """Fill in the secrets docker-compose requires, if the user has not set them."""
    defaults = {
        "POSTGRES_PASSWORD": DEV_POSTGRES_PASSWORD,
        "SENTINEL_AUTH_SECRET": DEV_AUTH_SECRET,
        "SENTINEL_ADMIN_PASSWORD": DEV_ADMIN_PASSWORD,
    }
    for key, value in defaults.items():
        if not os.environ.get(key):
            os.environ[key] = value
            log(f"using development default for {key} (set it yourself for production)")


def open_browser(url: str) -> None:
    log(f"opening {url}")
    try:
        webbrowser.open(url)
    except Exception:  # pragma: no cover - depends on the OS browser
        log("could not launch a browser automatically - open the URL manually")


def compose(*args: str) -> int:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.call(cmd, cwd=str(ROOT))


# --------------------------------------------------------------------------- modes
def run_docker(no_browser: bool = False, build: bool = False,
               start_desktop: bool = True) -> int:
    """Start the hardened 3-service stack (app + PostgreSQL + Redis)."""
    ensure_docker_on_path()
    if not have("docker"):
        log("ERROR: docker is not installed")
        log("       install Docker Desktop, or run: python execute.py --mode local")
        return 1
    if not docker_daemon_ready():
        if start_desktop and start_docker_desktop():
            pass
        else:
            log("ERROR: the Docker engine is not running - start Docker Desktop first")
            log("       or run: python execute.py --mode local")
            return 1

    apply_dev_env()

    if build or not image_exists("sentinel-ai:latest"):
        log("building the application image (first run takes a few minutes) ...")
    else:
        log("reusing the existing sentinel-ai image (use --build to rebuild)")

    log("starting: app + PostgreSQL + Redis ...")
    code = compose("up", "-d", *(["--build"] if (build or not image_exists("sentinel-ai:latest")) else []))
    if code != 0:
        log("ERROR: docker compose up failed")
        return code

    if not wait_for_http(f"{API_URL}/api/health", timeout=240, label="backend API"):
        log("check the logs with: docker compose logs -f sentinel-ai")
        return 1

    try:
        with urllib.request.urlopen(f"{API_URL}/api/system", timeout=5) as resp:
            system = resp.read().decode("utf-8", "replace")
        log(f"storage/cache: {system}")
    except (urllib.error.URLError, OSError):
        pass

    log("")
    log("  dashboard : " + DASHBOARD_URL)
    log("  api docs  : " + f"{API_URL}/docs")
    log(f"  login     : admin / {os.environ.get('SENTINEL_ADMIN_PASSWORD', DEV_ADMIN_PASSWORD)}")
    log("  stop      : press Ctrl+C here, or run: python execute.py --stop")
    log("")
    if not no_browser:
        open_browser(DASHBOARD_URL)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("")
        log("the stack keeps running - the dashboard is still available at "
            + DASHBOARD_URL)
        log("stop it with: python execute.py --stop")
    return 0


def run_local(no_browser: bool = False) -> int:
    """Start the FastAPI backend and the Vite dev server on this machine."""
    if not (BACKEND_DIR / "app" / "main.py").is_file():
        log(f"ERROR: backend not found at {BACKEND_DIR}")
        return 1
    if not have("npm"):
        log("ERROR: npm is not installed or not on PATH (Node.js 18+ required)")
        return 1

    if not (FRONTEND_DIR / "node_modules").is_dir():
        log("installing frontend dependencies (first run only) ...")
        code = subprocess.call(["npm.cmd" if os.name == "nt" else "npm", "install"],
                               cwd=str(FRONTEND_DIR))
        if code != 0:
            log("ERROR: npm install failed")
            return code

    procs: list[tuple[str, subprocess.Popen]] = []

    log(f"starting backend on :{API_PORT} ...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)],
        cwd=str(BACKEND_DIR))
    procs.append(("backend", backend))

    log(f"starting frontend on :{UI_PORT} ...")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    frontend = subprocess.Popen([npm, "run", "dev"], cwd=str(FRONTEND_DIR))
    procs.append(("frontend", frontend))

    api_up = wait_for_http(f"{API_URL}/api/health", timeout=120, label="backend API")
    ui_up = wait_for_http(UI_URL, timeout=120, label="frontend")
    if not (api_up and ui_up):
        for _, proc in procs:
            proc.terminate()

    log("")
    log("  dashboard : " + UI_URL)
    log("  api docs  : " + f"{API_URL}/docs")
    log("  login     : admin / admin123  (or SENTINEL_ADMIN_PASSWORD)")
    log("  stop      : press Ctrl+C here")
    log("")
    if not no_browser and api_up and ui_up:
        open_browser(UI_URL)

    try:
        while True:
            for name, proc in procs:
                if proc.poll() is not None:
                    log(f"{name} exited (code {proc.returncode})")
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        log("stopping the local servers ...")
        for _, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


def stop_stack() -> int:
    if not have("docker"):
        log("docker is not installed or not on PATH")
        return 1
    # compose interpolates the same variables at parse time, so they must be
    # present here too.
    apply_dev_env()
    log("stopping the stack (volumes are kept) ...")
    return compose("down")


# --------------------------------------------------------------------------- entry
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the whole Sentinel AI program from one file.")
    parser.add_argument("--mode", choices=["auto", "docker", "local"], default="auto",
                        help="auto (default): docker when the engine is up, else local")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the dashboard in a browser")
    parser.add_argument("--build", action="store_true",
                        help="rebuild the docker image before starting")
    parser.add_argument("--stop", action="store_true",
                        help="stop a running docker stack and exit")
    parser.add_argument("--no-start-docker", action="store_true",
                        help="do not launch Docker Desktop automatically")
    args = parser.parse_args(argv)

    if args.stop:
        return stop_stack()

    mode = args.mode
    if mode == "auto":
        ensure_docker_on_path()
        docker_installed = have("docker") and any(e.is_file() for e in DOCKER_DESKTOP_EXE)
        if docker_installed or docker_daemon_ready():
            mode = "docker"
        else:
            mode = "local"
        log(f"auto-detected mode: {mode}")

    if mode == "docker":
        return run_docker(no_browser=args.no_browser, build=args.build,
                          start_desktop=not args.no_start_docker)
    return run_local(no_browser=args.no_browser)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
